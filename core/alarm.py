"""
报警模块 - 支持多种报警规则和通知方式
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import pandas as pd


class AlarmLevel(Enum):
    """报警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlarmType(Enum):
    """报警类型"""
    THRESHOLD_HIGH = "threshold_high"      # 超上限
    THRESHOLD_LOW = "threshold_low"        # 超下限
    STALE_DATA = "stale_data"              # 数据停滞
    DEVICE_OFFLINE = "device_offline"      # 设备离线
    PARSE_ERROR = "parse_error"            # 解析错误
    RATE_OF_CHANGE = "rate_of_change"     # 变化率异常
    CUSTOM = "custom"                      # 自定义


@dataclass
class AlarmRule:
    """报警规则"""
    id: str
    name: str
    field: str                              # 监控的字段
    level: AlarmLevel = AlarmLevel.WARNING
    
    # 阈值配置
    threshold_high: Optional[float] = None  # 上限
    threshold_low: Optional[float] = None   # 下限
    
    # 数据停滞检测
    stale_threshold: Optional[int] = None   # 秒，超过此时间无数据视为停滞
    
    # 变化率检测
    max_rate_of_change: Optional[float] = None  # 最大变化率（每秒）
    
    # 状态
    enabled: bool = True
    triggered: bool = False                 # 是否已触发
    last_trigger_time: Optional[datetime] = None
    trigger_count: int = 0                 # 累计触发次数
    
    # 抑制（防止频繁报警）
    suppression_seconds: int = 60          # 触发后抑制多少秒
    last_alarm_time: Optional[datetime] = None
    
    # 标签
    tags: List[str] = field(default_factory=list)
    
    def is_in_suppression(self) -> bool:
        """是否处于抑制期"""
        if self.last_alarm_time is None:
            return False
        elapsed = (datetime.now() - self.last_alarm_time).total_seconds()
        return elapsed < self.suppression_seconds
    
    def should_alarm(self) -> bool:
        """是否应该报警"""
        if not self.enabled:
            return False
        if self.triggered and self.is_in_suppression():
            return False
        return True


@dataclass
class Alarm:
    """报警信息"""
    id: str
    rule_id: str
    rule_name: str
    level: AlarmLevel
    alarm_type: AlarmType
    message: str
    timestamp: datetime
    data: Dict[str, Any]
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'rule_name': self.rule_name,
            'level': self.level.value,
            'type': self.alarm_type.value,
            'message': self.message,
            'timestamp': self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'acknowledged': self.acknowledged,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_time': self.acknowledged_time.strftime("%Y-%m-%d %H:%M:%S") if self.acknowledged_time else None,
        }


class AlarmManager:
    """报警管理器"""
    
    def __init__(self):
        self._rules: Dict[str, AlarmRule] = {}
        self._alarms: List[Alarm] = []
        self._alarm_history: List[Alarm] = []  # 历史报警
        self._max_history = 1000
        
        # 回调函数
        self._on_alarm_callback: Optional[Callable[[Alarm], None]] = None
        self._on_alarm_clear_callback: Optional[Callable[[AlarmRule], None]] = None
        
        # 状态追踪
        self._field_history: Dict[str, List[tuple]] = {}  # field -> [(timestamp, value), ...]
        self._device_last_seen: Dict[str, datetime] = {}
        self._lock = threading.Lock()
        
        # 内置报警声音路径
        self._default_sound_file: Optional[Path] = None
        
    def add_rule(
        self,
        rule_id: str,
        name: str,
        field: str,
        level: AlarmLevel = AlarmLevel.WARNING,
        threshold_high: Optional[float] = None,
        threshold_low: Optional[float] = None,
        stale_threshold: Optional[int] = None,
        max_rate_of_change: Optional[float] = None,
        suppression_seconds: int = 60,
        tags: List[str] = None,
    ) -> AlarmRule:
        """添加报警规则"""
        rule = AlarmRule(
            id=rule_id,
            name=name,
            field=field,
            level=level,
            threshold_high=threshold_high,
            threshold_low=threshold_low,
            stale_threshold=stale_threshold,
            max_rate_of_change=max_rate_of_change,
            suppression_seconds=suppression_seconds,
            tags=tags or [],
        )
        
        with self._lock:
            self._rules[rule_id] = rule
            
        return rule
        
    def remove_rule(self, rule_id: str):
        """移除报警规则"""
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                
    def get_rule(self, rule_id: str) -> Optional[AlarmRule]:
        """获取报警规则"""
        return self._rules.get(rule_id)
        
    def update_rule(self, rule_id: str, **kwargs):
        """更新报警规则"""
        with self._lock:
            if rule_id in self._rules:
                rule = self._rules[rule_id]
                for key, value in kwargs.items():
                    if hasattr(rule, key):
                        setattr(rule, key, value)
                        
    def set_on_alarm(self, callback: Callable[[Alarm], None]):
        """设置报警回调"""
        self._on_alarm_callback = callback
        
    def set_on_alarm_clear(self, callback: Callable[[AlarmRule], None]):
        """设置报警清除回调"""
        self._on_alarm_clear_callback = callback
        
    def check_data(self, data: Dict[str, Any], device_id: str = "default"):
        """检查数据，触发报警"""
        timestamp = datetime.now()
        
        with self._lock:
            rules_to_check = [r for r in self._rules.values() if r.enabled]
            
        triggered_rules = []
        
        for rule in rules_to_check:
            if rule.field not in data:
                continue
                
            value = data[rule.field]
            
            if not isinstance(value, (int, float)):
                continue
                
            # 更新历史记录
            self._update_history(rule.field, timestamp, value)
            
            # 检查阈值
            alarm = None
            
            if rule.threshold_high is not None and value > rule.threshold_high:
                alarm = self._create_alarm(rule, AlarmType.THRESHOLD_HIGH, 
                    f"{rule.field}={value:.2f} 超过上限 {rule.threshold_high}", 
                    data, timestamp)
                    
            elif rule.threshold_low is not None and value < rule.threshold_low:
                alarm = self._create_alarm(rule, AlarmType.THRESHOLD_LOW,
                    f"{rule.field}={value:.2f} 低于下限 {rule.threshold_low}",
                    data, timestamp)
                    
            # 检查变化率
            if alarm is None and rule.max_rate_of_change is not None:
                rate = self._calculate_rate_of_change(rule.field)
                if rate is not None and abs(rate) > rule.max_rate_of_change:
                    alarm = self._create_alarm(rule, AlarmType.RATE_OF_CHANGE,
                        f"{rule.field}变化率={rate:.2f}/s 超过限制 {rule.max_rate_of_change}/s",
                        data, timestamp)
                        
            if alarm:
                triggered_rules.append((rule, alarm))
                
        # 更新设备最后活跃时间
        self._device_last_seen[device_id] = timestamp
        
        # 处理触发的报警
        for rule, alarm in triggered_rules:
            self._handle_alarm(rule, alarm)
            
        # 检查数据停滞
        self._check_stale_data(timestamp)
        
    def _update_history(self, field: str, timestamp: datetime, value: float):
        """更新历史数据"""
        if field not in self._field_history:
            self._field_history[field] = []
            
        history = self._field_history[field]
        history.append((timestamp, value))
        
        # 只保留最近100条
        if len(history) > 100:
            self._field_history[field] = history[-100:]
            
    def _calculate_rate_of_change(self, field: str) -> Optional[float]:
        """计算变化率"""
        if field not in self._field_history:
            return None
            
        history = self._field_history[field]
        if len(history) < 2:
            return None
            
        (t1, v1), (t2, v2) = history[-2], history[-1]
        dt = (t2 - t1).total_seconds()
        
        if dt <= 0:
            return None
            
        return (v2 - v1) / dt
        
    def _create_alarm(
        self,
        rule: AlarmRule,
        alarm_type: AlarmType,
        message: str,
        data: Dict[str, Any],
        timestamp: datetime
    ) -> Optional[Alarm]:
        """创建报警"""
        alarm_id = f"{rule.id}_{int(timestamp.timestamp() * 1000)}"
        
        alarm = Alarm(
            id=alarm_id,
            rule_id=rule.id,
            rule_name=rule.name,
            level=rule.level,
            alarm_type=alarm_type,
            message=message,
            timestamp=timestamp,
            data=data.copy(),
        )
        
        return alarm
        
    def _handle_alarm(self, rule: AlarmRule, alarm: Alarm):
        """处理报警"""
        if rule.should_alarm():
            # 添加到报警列表
            self._alarms.append(alarm)
            self._alarm_history.append(alarm)
            
            # 限制历史记录数量
            if len(self._alarm_history) > self._max_history:
                self._alarm_history = self._alarm_history[-self._max_history:]
                
            # 更新规则状态
            rule.triggered = True
            rule.last_trigger_time = alarm.timestamp
            rule.last_alarm_time = alarm.timestamp
            rule.trigger_count += 1
            
            # 触发回调
            if self._on_alarm_callback:
                self._on_alarm_callback(alarm)
                
    def _check_stale_data(self, timestamp: datetime):
        """检查数据停滞"""
        for rule in self._rules.values():
            if not rule.enabled or rule.stale_threshold is None:
                continue
                
            # 检查是否有新数据
            if rule.field in self._field_history:
                last_time = self._field_history[rule.field][-1][0]
                elapsed = (timestamp - last_time).total_seconds()
                
                if elapsed > rule.stale_threshold and not rule.is_in_suppression():
                    alarm = self._create_alarm(
                        rule,
                        AlarmType.STALE_DATA,
                        f"{rule.field} 数据停滞超过 {elapsed:.0f} 秒",
                        {},
                        timestamp
                    )
                    self._handle_alarm(rule, alarm)
                    
    def acknowledge_alarm(self, alarm_id: str, acknowledged_by: str = "user"):
        """确认报警"""
        with self._lock:
            for alarm in self._alarms:
                if alarm.id == alarm_id:
                    alarm.acknowledged = True
                    alarm.acknowledged_by = acknowledged_by
                    alarm.acknowledged_time = datetime.now()
                    break
                    
    def acknowledge_all(self, acknowledged_by: str = "user"):
        """确认所有报警"""
        with self._lock:
            for alarm in self._alarms:
                alarm.acknowledged = True
                alarm.acknowledged_by = acknowledged_by
                alarm.acknowledged_time = datetime.now()
                
    def clear_alarm(self, alarm_id: str):
        """清除报警"""
        with self._lock:
            self._alarms = [a for a in self._alarms if a.id != alarm_id]
            
    def clear_triggered_rules(self, rule_id: Optional[str] = None):
        """清除规则触发状态"""
        with self._lock:
            if rule_id:
                if rule_id in self._rules:
                    self._rules[rule_id].triggered = False
            else:
                for rule in self._rules.values():
                    rule.triggered = False
                    
    def get_active_alarms(self) -> List[Dict]:
        """获取当前活跃报警"""
        with self._lock:
            return [a.to_dict() for a in self._alarms if not a.acknowledged]
            
    def get_alarm_history(self, limit: int = 100) -> List[Dict]:
        """获取报警历史"""
        with self._lock:
            alarms = self._alarm_history[-limit:]
            return [a.to_dict() for a in alarms]
            
    def get_rules(self) -> List[AlarmRule]:
        """获取所有规则"""
        return list(self._rules.values())
        
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            return {
                'total_rules': len(self._rules),
                'active_alarms': len([a for a in self._alarms if not a.acknowledged]),
                'acknowledged_alarms': len([a for a in self._alarms if a.acknowledged]),
                'total_history': len(self._alarm_history),
                'triggered_rules': len([r for r in self._rules.values() if r.triggered]),
            }


# 默认报警规则工厂
def create_cold_storage_rules() -> List[Dict]:
    """创建冷库默认报警规则"""
    return [
        {
            'rule_id': 'temp_high',
            'name': '温度过高',
            'field': 'temperature',
            'level': AlarmLevel.WARNING,
            'threshold_high': 30,
            'suppression_seconds': 120,
        },
        {
            'rule_id': 'temp_low',
            'name': '温度过低',
            'field': 'temperature',
            'level': AlarmLevel.WARNING,
            'threshold_low': -35,
            'suppression_seconds': 120,
        },
        {
            'rule_id': 'humidity_high',
            'name': '湿度过高',
            'field': 'humidity',
            'level': AlarmLevel.INFO,
            'threshold_high': 85,
            'suppression_seconds': 300,
        },
        {
            'rule_id': 'humidity_low',
            'name': '湿度过低',
            'field': 'humidity',
            'level': AlarmLevel.WARNING,
            'threshold_low': 20,
            'suppression_seconds': 180,
        },
        {
            'rule_id': 'voltage_low',
            'name': '电压过低',
            'field': 'voltage',
            'level': AlarmLevel.CRITICAL,
            'threshold_low': 11.5,
            'suppression_seconds': 60,
        },
        {
            'rule_id': 'voltage_high',
            'name': '电压过高',
            'field': 'voltage',
            'level': AlarmLevel.ERROR,
            'threshold_high': 14.5,
            'suppression_seconds': 60,
        },
        {
            'rule_id': 'frost_high',
            'name': '结霜率过高',
            'field': 'frost',
            'level': AlarmLevel.WARNING,
            'threshold_high': 95,
            'suppression_seconds': 300,
        },
    ]
