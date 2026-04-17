"""
数据解析器 - 支持多种数据格式，可自定义解析规则
"""

import json
import re
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


class DataParser(ABC):
    """数据解析器基类"""
    
    @abstractmethod
    def parse(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """解析原始数据字符串"""
        pass
    
    @abstractmethod
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证解析后的数据"""
        pass


class CustomizableParser(DataParser):
    """可自定义的数据解析器"""
    
    # 支持的格式类型
    FORMAT_JSON = 'json'
    FORMAT_KEY_VALUE = 'key_value'  # T:25.5,H:60.2,V:12.3
    FORMAT_CSV = 'csv'              # 25.5,60.2,12.3
    FORMAT_DELIMITED = 'delimited' # 25.5|60.2|12.3
    FORMAT_FIXED = 'fixed'         # 固定位置解析
    
    def __init__(self):
        self._format_handlers: Dict[str, Callable] = {}
        self._field_order: List[str] = []
        self._regex_pattern: Optional[str] = None
        self._delimiter: str = ','
        self._expected_fields: Dict[str, Dict] = {}
        self._custom_parser: Optional[Callable] = None
        self._lock = threading.Lock()
        
        # 注册默认格式
        self._register_default_formats()
        
    def _register_default_formats(self):
        """注册默认格式处理器"""
        self._format_handlers = {
            self.FORMAT_JSON: self._parse_json,
            self.FORMAT_KEY_VALUE: self._parse_key_value,
            self.FORMAT_CSV: self._parse_csv,
            self.FORMAT_DELIMITED: self._parse_delimited,
        }
        
    def set_format(self, format_type: str, **kwargs):
        """设置解析格式"""
        with self._lock:
            if format_type == self.FORMAT_KEY_VALUE:
                self._field_order = kwargs.get('fields', [])
            elif format_type == self.FORMAT_CSV:
                self._field_order = kwargs.get('fields', [])
                self._delimiter = kwargs.get('delimiter', ',')
            elif format_type == self.FORMAT_DELIMITED:
                self._field_order = kwargs.get('fields', [])
                self._delimiter = kwargs.get('delimiter', '|')
            elif format_type == self.FORMAT_FIXED:
                self._field_order = kwargs.get('fields', [])
                self._widths = kwargs.get('widths', [])
            elif format_type == 'regex':
                self._regex_pattern = kwargs.get('pattern', '')
                self._field_order = kwargs.get('fields', [])
                
    def set_custom_parser(self, parser_func: Callable[[str], Optional[Dict]]):
        """设置自定义解析函数"""
        with self._lock:
            self._custom_parser = parser_func
            
    def set_expected_fields(self, fields: Dict[str, Dict]):
        """设置预期字段定义"""
        with self._lock:
            self._expected_fields = fields
            
    def parse(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """解析原始数据"""
        if not raw_data or not raw_data.strip():
            return None
            
        raw_data = raw_data.strip()
        
        with self._lock:
            # 优先使用自定义解析器
            if self._custom_parser:
                result = self._custom_parser(raw_data)
                if result:
                    return self._validate_and_normalize(result)
                return None
                
            # 尝试JSON格式
            try:
                result = self._parse_json(raw_data)
                if result and self.validate(result):
                    return self._validate_and_normalize(result)
            except:
                pass
                
            # 尝试键值对格式
            result = self._parse_key_value(raw_data)
            if result and self.validate(result):
                return self._validate_and_normalize(result)
                
            # 尝试CSV格式
            result = self._parse_csv(raw_data)
            if result and self.validate(result):
                return self._validate_and_normalize(result)
                
            # 尝试自定义分隔符格式
            result = self._parse_delimited(raw_data)
            if result and self.validate(result):
                return self._validate_and_normalize(result)
                
            return None
            
    def _validate_and_normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证并规范化数据"""
        if not data:
            return {}
            
        # 确保有timestamp
        if 'timestamp' not in data:
            data['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        # 类型转换和验证
        validated = {}
        for key, value in data.items():
            if key == 'timestamp':
                validated[key] = value
            elif isinstance(value, (int, float)):
                validated[key] = float(value)
            elif isinstance(value, str):
                try:
                    validated[key] = float(value)
                except ValueError:
                    validated[key] = value
            else:
                validated[key] = value
                
        return validated
        
    def _parse_json(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """解析JSON格式"""
        # 尝试直接解析
        try:
            return json.loads(raw_data)
        except:
            pass
            
        # 尝试提取JSON对象
        match = re.search(r'\{[^{}]*\}', raw_data)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
                
        return None
        
    def _parse_key_value(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """解析键值对格式，如 T:25.5,H:60.2"""
        result = {}
        
        # 多种分隔符支持
        pairs = re.split(r'[,;\s]+', raw_data.strip())
        
        for pair in pairs:
            if ':' in pair:
                key, value = pair.split(':', 1)
            elif '=' in pair:
                key, value = pair.split('=', 1)
            else:
                continue
                
            key = key.strip()
            value = value.strip()
            
            if key and value:
                try:
                    result[key] = float(value)
                except ValueError:
                    result[key] = value
                    
        return result if result else None
        
    def _parse_csv(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """解析CSV格式"""
        values = raw_data.split(self._delimiter)
        
        if not self._field_order:
            # 如果没有指定字段顺序，创建默认字段名
            self._field_order = [f'field_{i}' for i in range(len(values))]
            
        if len(values) != len(self._field_order):
            return None
            
        result = {}
        for field, value in zip(self._field_order, values):
            value = value.strip()
            try:
                result[field] = float(value)
            except ValueError:
                result[field] = value
                
        return result
        
    def _parse_delimited(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """解析分隔符格式"""
        return self._parse_csv(raw_data)
        
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证数据"""
        if not data:
            return False
            
        # 如果有预期字段定义，检查必填字段
        if self._expected_fields:
            for field, config in self._expected_fields.items():
                if config.get('required', False) and field not in data:
                    return False
                    
                # 范围检查
                if field in data and isinstance(data[field], (int, float)):
                    min_val = config.get('min')
                    max_val = config.get('max')
                    if min_val is not None and data[field] < min_val:
                        return False
                    if max_val is not None and data[field] > max_val:
                        return False
                        
        return True
        
    def add_format_handler(self, name: str, handler: Callable):
        """添加自定义格式处理器"""
        with self._lock:
            self._format_handlers[name] = handler
            
    def get_field_order(self) -> List[str]:
        """获取当前字段顺序"""
        with self._lock:
            return self._field_order.copy()


class ColdStorageDataParser(DataParser):
    """冷库专用数据解析器"""
    
    # 冷库数据字段映射
    FIELD_MAP = {
        'T': 'temperature',
        '温度': 'temperature',
        'H': 'humidity',
        '湿度': 'humidity',
        'V': 'voltage',
        '电压': 'voltage',
        'C': 'current',
        '电流': 'current',
        'P': 'power',
        '功率': 'power',
        'F': 'frost',
        '结霜': 'frost',
        'Comp': 'compressor',
        '压缩机': 'compressor',
        'Fan': 'fan',
        '风扇': 'fan',
        'Door': 'door',
        '门': 'door',
        'time': 'timestamp',
        'Time': 'timestamp',
        '时间': 'timestamp',
    }
    
    def __init__(self):
        self._expected_fields = ['temperature', 'humidity', 'voltage', 'current']
        
    def parse(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """解析冷库数据"""
        if not raw_data:
            return None
            
        raw_data = raw_data.strip()
        result = {}
        
        # 方法1: JSON格式
        if raw_data.startswith('{'):
            try:
                import json
                data = json.loads(raw_data)
                result = self._normalize_fields(data)
            except:
                pass
                
        # 方法2: 键值对格式 T:25.5,H:60.2,...
        if not result:
            result = self._parse_key_value(raw_data)
            
        # 方法3: 按顺序解析 T,H,V,C,F
        if not result:
            result = self._parse_ordered(raw_data)
            
        if result:
            result['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        return result
        
    def _normalize_fields(self, data: Dict) -> Dict[str, Any]:
        """规范化字段名"""
        result = {}
        for key, value in data.items():
            normalized = self.FIELD_MAP.get(key, key)
            result[normalized] = value
        return result
        
    def _parse_key_value(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """解析键值对"""
        result = {}
        
        # 支持多种分隔符
        pairs = re.split(r'[,;|]+', raw_data)
        
        for pair in pairs:
            if ':' in pair:
                key, value = pair.split(':', 1)
            elif '=' in pair:
                key, value = pair.split('=', 1)
            else:
                continue
                
            key = key.strip()
            value = value.strip()
            
            if key:
                normalized = self.FIELD_MAP.get(key, key)
                try:
                    result[normalized] = float(value)
                except ValueError:
                    result[normalized] = value
                    
        return result if result else None
        
    def _parse_ordered(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """按顺序解析"""
        values = re.split(r'[,;\s]+', raw_data.strip())
        
        if len(values) < 4:
            return None
            
        result = {}
        for i, (field, value) in enumerate(zip(self._expected_fields, values)):
            try:
                result[field] = float(value.strip())
            except ValueError:
                return None
                
        # 可选的结霜率
        if len(values) > 4:
            try:
                result['frost'] = float(values[4].strip())
            except ValueError:
                pass
                
        return result
        
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证数据"""
        if not data:
            return False
            
        # 检查必要字段
        for field in ['temperature', 'humidity', 'voltage']:
            if field not in data:
                return False
            if not isinstance(data[field], (int, float)):
                return False
                
        return True
