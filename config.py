"""
配置文件 - 串口监控系统
支持 Windows / Linux / Mac
"""

import os
from pathlib import Path

# ========== 项目路径 ==========
BASE_DIR = Path(__file__).parent.absolute()
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
CONFIG_FILE = BASE_DIR / "config.json"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ========== 串口默认配置 ==========
SERIAL_DEFAULTS = {
    "baudrate": 115200,      # 波特率
    "bytesize": 8,           # 数据位
    "parity": 'N',           # 校验位
    "stopbits": 1,           # 停止位
    "timeout": 1,            # 读取超时(秒)
}

# ========== 数据字段定义 ==========
# 支持自定义字段，可扩展
DEFAULT_FIELDS = {
    "temperature": {"name": "温度", "unit": "°C", "min": -50, "max": 100, "default_min": -30, "default_max": 50},
    "humidity": {"name": "湿度", "unit": "%", "min": 0, "max": 100, "default_min": 30, "default_max": 80},
    "voltage": {"name": "电压", "unit": "V", "min": 0, "max": 30, "default_min": 11, "default_max": 14},
    "current": {"name": "电流", "unit": "A", "min": 0, "max": 20, "default_min": 0, "default_max": 10},
    "power": {"name": "功率", "unit": "W", "min": 0, "max": 5000, "default_min": 0, "default_max": 3000},
    "pressure": {"name": "压力", "unit": "kPa", "min": 0, "max": 1000, "default_min": 100, "default_max": 300},
}

# ========== 报警配置 ==========
ALARM_DEFAULTS = {
    "enabled": True,
    "sound": True,
    "popup": True,
    "sound_file": None,  # 自定义报警音路径
}

# ========== 数据存储配置 ==========
STORAGE_DEFAULTS = {
    "auto_save_interval": 60,      # 自动保存间隔(秒)
    "max_records_in_memory": 10000, # 内存中最大记录数
    "file_format": "csv",           # csv 或 excel
}

# ========== 模拟器配置 ==========
SIMULATOR_DEFAULTS = {
    "interval": 1,                 # 数据生成间隔(秒)
    "noise_level": 0.1,            # 噪声级别(0-1)
    "scenario": "cold_storage",     # 默认场景
}

# ========== 平台检测 ==========
def get_platform():
    """获取当前平台"""
    import sys
    if sys.platform.startswith('win'):
        return 'windows'
    elif sys.platform.startswith('linux'):
        return 'linux'
    elif sys.platform.startswith('darwin'):
        return 'mac'
    return 'unknown'

# ========== 串口列表获取 ==========
def list_serial_ports():
    """获取可用串口列表"""
    import sys
    import serial.tools.list_ports
    
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

# ========== 配置文件操作 ==========
def load_config():
    """加载配置文件"""
    import json
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(config):
    """保存配置文件"""
    import json
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    print(f"平台: {get_platform()}")
    print(f"可用串口: {list_serial_ports()}")
