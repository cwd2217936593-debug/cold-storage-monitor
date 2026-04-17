"""
冷库模拟器 - 模拟冷库传感器数据
"""

import random
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from config import DEFAULT_FIELDS


class ColdStorageSimulator:
    """
    冷库模拟器
    
    模拟以下场景:
    - 正常制冷运行
    - 温度异常升高
    - 湿度变化
    - 电压波动
    - 设备开关状态
    - 结霜周期
    """
    
    def __init__(
        self,
        interval: float = 1.0,
        noise_level: float = 0.05,
        data_format: str = "key_value"
    ):
        self.interval = interval
        self.noise_level = noise_level
        self.data_format = data_format
        
        # 状态
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._data_callback: Optional[Callable[[Dict], None]] = None
        
        # 冷库状态
        self._state = {
            'temperature': -25.0,        # 温度 (°C)
            'humidity': 60.0,            # 湿度 (%)
            'voltage': 12.6,             # 电压 (V)
            'current': 5.0,              # 电流 (A)
            'power': 63.0,              # 功率 (W)
            'frost': 50.0,              # 结霜率 (%)
            'comp': 1,                  # 压缩机 0=关闭 1=开启
            'fan': 1,                   # 风扇 0=关闭 1=开启
            'door': 0,                  # 门 0=关闭 1=开启
        }
        
        # 运行参数
        self._target_temp = -25.0       # 目标温度
        self._ambient_temp = 25.0       # 环境温度
        self._cooling_rate = 0.5        # 制冷速率
        self._warming_rate = 0.3       # 升温速率
        
        # 霜冻周期
        self._frost_phase = 0           # 0-100 循环
        self._frost_direction = 1      # 1=增长 -1=减少
        
        # 事件
        self._current_event: Optional[str] = None
        self._event_duration = 0
        self._event_timer = 0
        
        # 数据计数器
        self._data_count = 0
        
    def set_callback(self, callback: Callable[[Dict], None]):
        """设置数据回调"""
        self._data_callback = callback
        
    def start(self):
        """开始模拟"""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        """停止模拟"""
        self._running = False
        
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
            
    def _run_loop(self):
        """运行循环"""
        while self._running:
            # 更新状态
            self._update_state()
            
            # 生成数据
            data = self._generate_data()
            
            # 触发回调
            if self._data_callback:
                self._data_callback(data)
                
            self._data_count += 1
            time.sleep(self.interval)
            
    def _update_state(self):
        """更新冷库状态"""
        # 处理事件
        self._process_events()
        
        # 温度控制
        if self._state['comp'] == 1 and self._state['door'] == 0:
            # 制冷中
            if self._state['temperature'] > self._target_temp:
                self._state['temperature'] -= self._cooling_rate * (1 + random.uniform(-0.2, 0.2))
            else:
                # 温度达到目标，压缩机可能间歇运行
                self._state['comp'] = random.choice([1, 1, 1, 0])  # 75%时间开启
        else:
            # 停机或开门，升温
            if self._state['door'] == 1:
                # 开门时升温更快
                self._state['temperature'] += (self._warming_rate * 3 + 
                    (self._ambient_temp - self._state['temperature']) * 0.02)
                self._state['humidity'] -= 0.5  # 开门湿度下降
            else:
                self._state['temperature'] += self._warming_rate * (1 + random.uniform(-0.2, 0.2))
                
        # 湿度控制
        if self._state['door'] == 0 and self._state['temperature'] < -20:
            # 密闭低温环境，湿度缓慢上升
            self._state['humidity'] += random.uniform(0.1, 0.3)
        self._state['humidity'] = max(20, min(95, self._state['humidity']))
        
        # 电压模拟
        self._state['voltage'] = 12.6 + random.uniform(-0.3, 0.3)
        if self._state['comp'] == 1:
            self._state['voltage'] -= 0.2
        self._state['voltage'] = max(11.0, min(13.5, self._state['voltage']))
        
        # 电流和功率
        self._state['current'] = 3.0 if self._state['comp'] == 0 else 5.0
        self._state['current'] += random.uniform(-0.3, 0.3)
        self._state['power'] = self._state['voltage'] * self._state['current']
        
        # 风扇
        self._state['fan'] = 1 if self._state['comp'] == 1 else 0
        
        # 结霜率（周期性变化）
        self._update_frost()
        
        # 添加噪声
        self._add_noise()
        
    def _update_frost(self):
        """更新结霜率"""
        # 结霜与温度和运行时间相关
        if self._state['comp'] == 1 and self._state['fan'] == 1:
            # 制冷运行时结霜增加
            self._frost_phase += 0.3 + random.uniform(0, 0.2)
        else:
            # 停机时结霜可能融化
            self._frost_phase -= 0.1
            
        # 限制范围
        self._frost_phase = max(0, min(100, self._frost_phase))
        
        self._state['frost'] = self._frost_phase
        
    def _add_noise(self):
        """添加噪声"""
        for key in ['temperature', 'humidity', 'voltage', 'current', 'power']:
            noise = random.gauss(0, self.noise_level)
            self._state[key] += noise
            
    def _process_events(self):
        """处理随机事件"""
        self._event_timer += self.interval
        
        if self._current_event is None:
            # 随机选择事件
            self._select_event()
        elif self._event_timer >= self._event_duration:
            # 事件结束
            self._end_event()
            
        # 根据当前事件调整参数
        self._apply_event_effects()
        
    def _select_event(self):
        """选择事件"""
        events = [
            ('normal', 70),           # 正常运行
            ('door_open', 15),         # 开门
            ('temp_rise', 10),         # 温度异常
            ('power_spike', 5),        # 电压波动
        ]
        
        # 按权重选择
        r = random.uniform(0, sum(e[1] for e in events))
        cumulative = 0
        for event, weight in events:
            cumulative += weight
            if r <= cumulative:
                self._current_event = event
                break
                
        # 设置事件参数
        if self._current_event == 'door_open':
            self._event_duration = random.uniform(10, 30)
            self._state['door'] = 1
        elif self._current_event == 'temp_rise':
            self._event_duration = random.uniform(20, 60)
            self._target_temp = random.uniform(-15, -10)  # 目标温度升高
        elif self._current_event == 'power_spike':
            self._event_duration = random.uniform(5, 15)
            
        self._event_timer = 0
        
    def _end_event(self):
        """结束事件"""
        if self._current_event == 'door_open':
            self._state['door'] = 0
        elif self._current_event == 'temp_rise':
            self._target_temp = -25.0  # 恢复正常目标温度
        elif self._current_event == 'power_spike':
            pass
            
        self._current_event = None
        self._event_timer = 0
        
    def _apply_event_effects(self):
        """应用事件效果"""
        if self._current_event == 'power_spike':
            self._state['voltage'] += random.uniform(-2, 2)
            
    def _generate_data(self) -> Dict:
        """生成数据"""
        data = {
            'timestamp': datetime.now(),
            **self._state.copy()
        }
        
        if self.data_format == 'key_value':
            # 键值对格式
            data['_format'] = 'key_value'
            data['_raw'] = self._format_key_value()
        elif self.data_format == 'csv':
            data['_format'] = 'csv'
            data['_raw'] = self._format_csv()
        elif self.data_format == 'json':
            data['_format'] = 'json'
            data['_raw'] = self._format_json()
            
        return data
        
    def _format_key_value(self) -> str:
        """键值对格式 T:-25.5,H:60.2,V:12.3"""
        return (f"T:{self._state['temperature']:.1f},"
                f"H:{self._state['humidity']:.1f},"
                f"V:{self._state['voltage']:.2f},"
                f"C:{self._state['current']:.1f},"
                f"F:{self._state['frost']:.1f}")
                
    def _format_csv(self) -> str:
        """CSV格式 -25.5,60.2,12.3,5.0,50.0"""
        return (f"{self._state['temperature']:.1f},"
                f"{self._state['humidity']:.1f},"
                f"{self._state['voltage']:.2f},"
                f"{self._state['current']:.1f},"
                f"{self._state['frost']:.1f}")
                
    def _format_json(self) -> str:
        """JSON格式"""
        import json
        return json.dumps({
            'temperature': round(self._state['temperature'], 1),
            'humidity': round(self._state['humidity'], 1),
            'voltage': round(self._state['voltage'], 2),
            'current': round(self._state['current'], 1),
            'frost': round(self._state['frost'], 1),
            'comp': self._state['comp'],
            'fan': self._state['fan'],
            'door': self._state['door'],
        })
        
    def get_current_state(self) -> Dict:
        """获取当前状态"""
        return self._state.copy()
        
    def set_parameter(self, key: str, value):
        """设置参数"""
        if key in self._state:
            self._state[key] = value
        elif key == 'target_temp':
            self._target_temp = value
        elif key == 'ambient_temp':
            self._ambient_temp = value
        elif key == 'cooling_rate':
            self._cooling_rate = value
            
    def trigger_event(self, event_name: str, duration: float = 30):
        """触发指定事件"""
        self._current_event = event_name
        self._event_duration = duration
        self._event_timer = 0
        
    def get_event_name(self) -> str:
        """获取当前事件名称"""
        return self._current_event or 'normal'
        
    def reset(self):
        """重置状态"""
        self._state = {
            'temperature': -25.0,
            'humidity': 60.0,
            'voltage': 12.6,
            'current': 5.0,
            'power': 63.0,
            'frost': 50.0,
            'comp': 1,
            'fan': 1,
            'door': 0,
        }
        self._target_temp = -25.0
        self._frost_phase = 50.0
        self._current_event = None
        self._data_count = 0


class MultiDeviceSimulator:
    """多设备模拟器"""
    
    def __init__(self):
        self._simulators: Dict[str, ColdStorageSimulator] = {}
        self._lock = threading.Lock()
        
    def add_device(self, name: str, **kwargs) -> ColdStorageSimulator:
        """添加设备模拟器"""
        with self._lock:
            sim = ColdStorageSimulator(**kwargs)
            self._simulators[name] = sim
            return sim
            
    def remove_device(self, name: str):
        """移除设备模拟器"""
        with self._lock:
            if name in self._simulators:
                self._simulators[name].stop()
                del self._simulators[name]
                
    def get_simulator(self, name: str) -> Optional[ColdStorageSimulator]:
        """获取模拟器"""
        return self._simulators.get(name)
        
    def start_all(self):
        """启动所有模拟器"""
        with self._lock:
            for sim in self._simulators.values():
                sim.start()
                
    def stop_all(self):
        """停止所有模拟器"""
        with self._lock:
            for sim in self._simulators.values():
                sim.stop()
                
    def list_devices(self) -> List[str]:
        """列出所有设备"""
        return list(self._simulators.keys())
