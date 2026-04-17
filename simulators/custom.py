"""
自定义模拟器模板 - 用户可在此基础上创建自己的模拟器
"""

import random
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any


class CustomSimulator:
    """
    自定义模拟器基类
    
    使用方法:
    1. 继承此类
    2. 实现 _init_state() 方法初始化状态
    3. 实现 _update_state() 方法更新状态
    4. 实现 _format_data() 方法格式化输出
    
    示例见下面的 TemperatureSimulator 和 PressureSimulator
    """
    
    def __init__(
        self,
        interval: float = 1.0,
        noise_level: float = 0.05,
        output_format: str = "json"
    ):
        self.interval = interval
        self.noise_level = noise_level
        self.output_format = output_format
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._data_callback: Optional[Callable[[Dict], None]] = None
        
        # 初始化状态
        self._state = self._init_state()
        
    def _init_state(self) -> Dict[str, Any]:
        """初始化状态，子类重写"""
        return {}
        
    def _update_state(self):
        """更新状态，子类重写"""
        pass
        
    def _format_data(self) -> str:
        """格式化数据输出，子类重写"""
        import json
        return json.dumps(self._state)
        
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
            self._update_state()
            
            data = {
                'timestamp': datetime.now(),
                **self._state.copy()
            }
            
            if self._data_callback:
                self._data_callback(data)
                
            time.sleep(self.interval)
            
    def get_current_state(self) -> Dict:
        """获取当前状态"""
        return self._state.copy()


class TemperatureSimulator(CustomSimulator):
    """温度传感器模拟器"""
    
    def _init_state(self) -> Dict:
        return {
            'temperature': 25.0,
            'humidity': 50.0,
            'unit': 'celsius',
        }
        
    def _update_state(self):
        # 温度波动
        self._state['temperature'] += random.gauss(0, self.noise_level)
        self._state['temperature'] = max(-50, min(100, self._state['temperature']))
        
        # 湿度与温度相关
        self._state['humidity'] += random.gauss(0, 0.2)
        self._state['humidity'] = max(0, min(100, self._state['humidity']))


class PressureSimulator(CustomSimulator):
    """压力传感器模拟器"""
    
    def _init_state(self) -> Dict:
        return {
            'pressure': 101.325,
            'altitude': 0,
            'unit': 'kPa',
        }
        
    def _update_state(self):
        # 压力波动（模拟天气变化）
        self._state['pressure'] += random.gauss(0, 0.05)
        self._state['pressure'] = max(80, min(110, self._state['pressure']))
        
        # 简化高度计算
        self._state['altitude'] = (101.325 - self._state['pressure']) * 8.5


class PowerMeterSimulator(CustomSimulator):
    """功率计模拟器"""
    
    def _init_state(self) -> Dict:
        return {
            'voltage': 220.0,
            'current': 0.0,
            'power': 0.0,
            'energy': 0.0,
            'frequency': 50.0,
            'pf': 0.95,
        }
        
    def _update_state(self):
        # 电压波动
        self._state['voltage'] = 220.0 + random.gauss(0, 2)
        self._state['voltage'] = max(210, min(230, self._state['voltage']))
        
        # 电流随机变化
        self._state['current'] = max(0, self._state['current'] + random.gauss(0, 0.5))
        
        # 功率计算
        self._state['power'] = self._state['voltage'] * self._state['current'] * self._state['pf']
        
        # 累计能耗 (kWh)
        self._state['energy'] += self._state['power'] * self.interval / 3600 / 1000


class EnvironmentMonitorSimulator(CustomSimulator):
    """环境监测仪模拟器"""
    
    def _init_state(self) -> Dict:
        return {
            'temperature': 25.0,
            'humidity': 60.0,
            'co2': 400.0,
            'pm25': 20.0,
            'lux': 300.0,
            'noise': 45.0,
        }
        
    def _update_state(self):
        # 温度
        self._state['temperature'] += random.gauss(0, self.noise_level)
        
        # 湿度
        self._state['humidity'] += random.gauss(0, 0.3)
        self._state['humidity'] = max(20, min(90, self._state['humidity']))
        
        # CO2（与人活动相关，模拟波动）
        self._state['co2'] += random.gauss(0, 5)
        self._state['co2'] = max(350, min(2000, self._state['co2']))
        
        # PM2.5（模拟空气质量波动）
        self._state['pm25'] += random.gauss(0, 1)
        self._state['pm25'] = max(0, min(500, self._state['pm25']))
        
        # 光照（模拟白天变化）
        self._state['lux'] += random.gauss(0, 10)
        self._state['lux'] = max(0, min(100000, self._state['lux']))
        
        # 噪声
        self._state['noise'] += random.gauss(0, 2)
        self._state['noise'] = max(20, min(120, self._state['noise']))


class CustomSimulatorFactory:
    """模拟器工厂"""
    
    _simulators = {
        'cold_storage': 'ColdStorageSimulator',  # 冷库模拟器
        'dht11': 'DHT11Simulator',             # DHT11 温湿度传感器模拟器
        'temperature': 'TemperatureSimulator',
        'pressure': 'PressureSimulator',
        'power': 'PowerMeterSimulator',
        'environment': 'EnvironmentMonitorSimulator',
    }
    
    @classmethod
    def create(cls, simulator_type: str, **kwargs) -> CustomSimulator:
        """创建模拟器"""
        if simulator_type == 'cold_storage':
            from .cold_storage import ColdStorageSimulator
            return ColdStorageSimulator(**kwargs)
        elif simulator_type == 'dht11':
            from .dht11 import DHT11Simulator
            return DHT11Simulator(**kwargs)
        elif simulator_type == 'temperature':
            return TemperatureSimulator(**kwargs)
        elif simulator_type == 'pressure':
            return PressureSimulator(**kwargs)
        elif simulator_type == 'power':
            return PowerMeterSimulator(**kwargs)
        elif simulator_type == 'environment':
            return EnvironmentMonitorSimulator(**kwargs)
        else:
            raise ValueError(f"未知模拟器类型: {simulator_type}")
            
    @classmethod
    def list_types(cls) -> List[str]:
        """列出所有支持的模拟器类型"""
        return list(cls._simulators.keys())


# 示例：如何创建自定义模拟器
if __name__ == "__main__":
    """
    自定义模拟器示例
    """
    
    class MyCustomSimulator(CustomSimulator):
        def _init_state(self) -> Dict:
            return {
                'value1': 0,
                'value2': 100,
                'status': 'normal',
            }
            
        def _update_state(self):
            self._state['value1'] += random.randint(-5, 5)
            self._state['value1'] = max(0, min(100, self._state['value1']))
            self._state['value2'] *= random.uniform(0.95, 1.05)
            
            if self._state['value1'] > 80:
                self._state['status'] = 'warning'
            elif self._state['value1'] < 20:
                self._state['status'] = 'critical'
            else:
                self._state['status'] = 'normal'
    
    # 使用
    sim = MyCustomSimulator(interval=1.0, noise_level=0.1)
    
    def on_data(data):
        print(f"[{data['timestamp']}] {data['value1']}, {data['value2']:.2f}, {data['status']}")
        
    sim.set_callback(on_data)
    sim.start()
    
    # 运行10秒后停止
    time.sleep(10)
    sim.stop()
