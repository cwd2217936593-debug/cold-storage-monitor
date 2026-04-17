# 冷库数据监控系统

跨平台（Windows / Linux / Mac）串口数据监控系统，支持实时监控、数据存储、报警提醒和多设备管理。

## 功能特性

### 三种运行模式

| 模式 | 入口文件 | 说明 |
|------|---------|------|
| tkinter 桌面版 | `serial_monitor.py` | 原生 GUI，无需浏览器 |
| Streamlit Web版 | `app.py` | 浏览器访问 localhost:8503 |
| Flask 网页版 | `flask_app.py` | 独立 Flask 服务，端口 5000 |
| pywebview 桌面版 | `desktop_app.py` | 轻量桌面窗口，内嵌 Web 界面 |

### 核心功能

- **串口数据读取** - 支持多种波特率和数据格式（JSON、键值对、CSV）
- **内置模拟器** - 无需硬件即可测试，支持冷库环境/温度/压力/功率/自定义场景
- **实时图表** - 多指标趋势可视化
- **报警管理** - 阈值超标报警，支持声音弹窗
- **数据导出** - CSV 和 Excel 格式
- **AI 趋势分析** - 基于历史数据预测温度/湿度走势
- **多设备支持** - 同时监控多个串口设备

### 支持的数据格式

```
# JSON 格式
{"temperature": 25.5, "humidity": 60.2, "voltage": 12.3}

# 键值对格式
T:25.5,H:60.2,V:12.3,C:5.0,F:50.0

# CSV 格式
25.5,60.2,12.3
```

## 项目结构

```
serial_monitor/
├── serial_monitor.py       # tkinter 原生桌面版（主程序）
├── app.py                  # Streamlit Web 版
├── flask_app.py           # Flask 独立网页版
├── desktop_app.py          # pywebview 桌面版
├── desktop_app.pyw         # pywebview 无控制台版本
├── ai_analysis.py         # AI 趋势分析模块
├── config.py              # 配置文件
├── requirements.txt       # 依赖列表
├── build_exe.py           # PyInstaller 打包脚本
├── core/                  # 核心模块
│   ├── serial_reader.py   # 串口读取、多端口管理
│   ├── data_parser.py     # 数据解析（冷库/自定义格式）
│   └── alarm.py           # 报警管理
├── simulators/            # 内置模拟器
│   ├── cold_storage.py    # 冷库环境模拟器（温度/湿度/电压/结霜率）
│   ├── dht11.py           # DHT11 温湿度传感器模拟器
│   └── custom.py          # 自定义模拟器模板
├── storage/               # 数据存储
│   └── data_storage.py    # CSV/Excel 导出
├── data/                  # 数据存储目录
├── icons/                 # 应用图标
└── dist/                  # 打包产物（exe）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或手动安装核心依赖：

```bash
pip install pyserial pandas openpyxl streamlit plotly
```

### 2. 使用模拟器测试（无需硬件）

```bash
# tkinter 版 - 自动使用冷库模拟器
python serial_monitor.py

# Streamlit 版
streamlit run app.py --server.port 8503

# Flask 版
python flask_app.py
```

然后访问 http://localhost:8503 或 http://127.0.0.1:5000

### 3. 连接真实硬件

在界面中选择串口（如 COM3）和波特率，点击连接即可。

推荐参数（冷库设备）：
- 波特率：115200
- 数据位：8
- 校验位：无
- 停止位：1

### 4. 打包为 exe

```bash
python build_exe.py
```

生成的 exe 在 `dist/SerialMonitor.exe`。

## 模拟器使用

### 内置模拟器

| 类型 | 说明 | 关键参数 |
|------|------|---------|
| `cold_storage` | 冷库环境（温度/湿度/电压/结霜率） | 目标温度、制冷功率、开门频率 |
| `dht11` | DHT11 温湿度传感器 | 量程截断特性（0~50C，20~90%RH） |
| `temperature` | 通用温度传感器 | 基础值、波动幅度 |
| `pressure` | 压力传感器 | 基础值、噪声级别 |
| `power` | 功率计 | 基础功率 |
| `environment` | 综合环境监测 | 多参数联合模拟 |

### 自定义模拟器

```python
from simulators.custom import CustomSimulator

class MySimulator(CustomSimulator):
    def _init_state(self):
        return {'value': 0, 'status': 'normal'}

    def _update_state(self):
        self._state['value'] += random.uniform(-5, 5)
        self._state['status'] = 'normal' if abs(self._state['value']) < 50 else 'warning'

sim = MySimulator(interval=1.0)
sim.set_callback(lambda data: print(data))
sim.start()
```

## 报警配置

```python
from core.alarm import AlarmManager, AlarmLevel

alarm_mgr = AlarmManager()

# 添加温度过高报警
alarm_mgr.add_rule(
    rule_id='temp_high',
    name='温度过高',
    field='temperature',
    level=AlarmLevel.WARNING,
    threshold_high=30.0,
    suppression_seconds=60  # 60秒内不重复报警
)

# 检查数据
alarm_mgr.check_data({'temperature': 35.0})
```

## 作为模块使用

```python
from serial_monitor import SerialReader, ColdStorageSimulator
from serial_monitor.core import DataParser, AlarmManager
from serial_monitor.storage import DataStorage

# 使用模拟器
simulator = ColdStorageSimulator()
simulator.set_callback(lambda data: print(data))
simulator.start()

# 使用真实串口
reader = SerialReader('COM3', 115200)
reader.connect()
reader.start()

# 存储数据
storage = DataStorage('data.csv')
storage.save(data)
```

## 技术栈

- Python 3.8+
- tkinter / Streamlit / Flask / pywebview（界面）
- Plotly（图表）
- Pandas / openpyxl（数据处理）
- pyserial（串口通信）
- LightGBM（AI 趋势预测）

## 平台支持

- Windows 10 / 11
- Linux（Ubuntu, Debian, CentOS 等）
- macOS

## License

MIT License
