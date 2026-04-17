# 串口数据监控系统

跨平台（Windows / Linux / Mac）串口数据监控系统，支持实时监控、数据存储、报警提醒和多设备管理。

## 功能特性

### 核心功能
- 📡 **串口数据读取** - 支持多种波特率和数据格式
- 🎭 **模拟器模式** - 内置多种模拟器，无需硬件即可测试
- 💾 **数据存储** - 支持CSV和Excel导出
- 📊 **实时图表** - 多指标趋势可视化
- ⚠️ **报警提醒** - 阈值超限报警
- 🔗 **多设备支持** - 同时监控多个串口设备

### 支持的数据格式
- JSON格式
- 键值对格式 (T:25.5,H:60.2,V:12.3)
- CSV格式
- 自定义分隔符格式

### 模拟器类型
| 类型 | 说明 |
|------|------|
| cold_storage | 🧊 冷库环境（温度、湿度、电压、结霜率） |
| temperature | 🌡️ 温度传感器 |
| pressure | 📊 压力传感器 |
| power | ⚡ 功率计 |
| environment | 🌍 环境监测仪 |

## 项目结构

```
serial_monitor/
├── serial_monitor.py      # tkinter桌面版
├── web_app.py             # Web版本 (Streamlit)
├── config.py              # 配置文件
├── requirements.txt       # 依赖列表
├── core/                  # 核心模块
│   ├── serial_reader.py   # 串口读取
│   ├── data_parser.py     # 数据解析
│   └── alarm.py           # 报警管理
├── simulators/            # 模拟器
│   ├── cold_storage.py    # 冷库模拟器
│   └── custom.py          # 自定义模拟器模板
├── storage/              # 存储模块
│   └── data_storage.py   # 数据存储导出
└── data/                 # 数据存储目录
```

## 安装依赖

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install pyserial pandas openpyxl streamlit plotly
```

## 使用方法

### 1. tkinter桌面版

```bash
cd serial_monitor
python serial_monitor.py
```

### 2. Web版本

```bash
cd serial_monitor
streamlit run web_app.py --server.port 8503
```

然后浏览器访问 http://localhost:8503

### 3. 作为模块使用

```python
from serial_monitor import SerialReader, ColdStorageSimulator
from serial_monitor.core import DataParser, AlarmManager
from serial_monitor.storage import DataStorage

# 使用模拟器
simulator = ColdStorageSimulator()
simulator.set_callback(lambda data: print(data))
simulator.start()

# 使用串口
reader = SerialReader('COM3', 115200)
reader.connect()
reader.start()
```

## 数据格式示例

### JSON格式
```json
{
    "temperature": 25.5,
    "humidity": 60.2,
    "voltage": 12.3,
    "timestamp": "2024-01-01 12:00:00"
}
```

### 键值对格式
```
T:25.5,H:60.2,V:12.3,C:5.0,F:50.0
```

### CSV格式
```
25.5,60.2,12.3,5.0,50.0
```

## 自定义模拟器

```python
from serial_monitor.simulators.custom import CustomSimulator
import random

class MySimulator(CustomSimulator):
    def _init_state(self):
        return {'value': 0, 'status': 'normal'}
    
    def _update_state(self):
        self._state['value'] += random.uniform(-5, 5)

sim = MySimulator(interval=1.0)
sim.set_callback(lambda data: print(data))
sim.start()
```

## 报警规则配置

```python
from serial_monitor.core.alarm import AlarmManager, AlarmLevel

alarm_mgr = AlarmManager()

# 添加报警规则
alarm_mgr.add_rule(
    rule_id='temp_high',
    name='温度过高',
    field='temperature',
    level=AlarmLevel.WARNING,
    threshold_high=30.0,
    suppression_seconds=60
)

# 检查数据
alarm_mgr.check_data({'temperature': 35.0})
```

## 平台支持

- ✅ Windows 10/11
- ✅ Linux (Ubuntu, Debian, CentOS等)
- ✅ macOS

## 技术栈

- Python 3.8+
- tkinter (桌面版GUI)
- Streamlit (Web版)
- Plotly (图表)
- Pandas (数据处理)
- pyserial (串口通信)

## License

MIT License
