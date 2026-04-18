# STM32F103C8T6 DHT11 温湿度监控

## 项目说明

基于 STM32F103C8T6 的 DHT11 温湿度传感器实时监控系统。  
使用 Keil MDK (ARMCC) 编译，ST-Link V2 (SWD) 或串口 ISP 烧录。

## 硬件

| 组件 | 型号 | 连接 |
|------|------|------|
| MCU | STM32F103C8T6 | - |
| 温湿度传感器 | DHT11 | DATA → PA0, VCC → 3.3V, GND → GND |
| LED | - | PB12 → GND (串联限流电阻) |
| 串口 | USART1 | PA9(TX) → CH340 RX, PA10(RX) → CH340 TX |
| 调试器 | ST-Link V2 | SWDIO/SWCLK |

## 时钟配置

- 使用 HSI 内部 8MHz RC 振荡器，不依赖外部 HSE
- SystemInit 为空函数，上电直接运行

## 串口参数

- 波特率: 9600 (8N1)
- USART1: PA9(TX), PA10(RX)
- 输出格式: `T:25C H:38%`

## 目录结构

```
stm32f1_led_pa0/
├── src/
│   ├── main.c                  # 主程序 (DHT11 + USART1 + LED)
│   ├── startup_stm32f103xb.s  # 启动文件 (Cortex-M3)
│   └── system_stm32f1xx.c     # 系统初始化 (空SystemInit, HSI 8MHz)
├── scripts/
│   └── build.bat               # Keil ARMCC 构建脚本
├── flash.py                    # pyocd SWD 烧录工具
├── monitor_continuous.py       # 持续监控 + 写 Excel (后台运行)
├── temp_humidity_logger.py     # 批量采集 + 写 Excel
└── out/                        # 编译输出 (led.bin, led.axf)
```

## 编译

```batch
cd stm32f1_led_pa0
scripts\build.bat
```

需要 Keil MDK 安装在 `D:\app\keil5MDK\ARM`

## 烧录

### ST-Link SWD (推荐)

```bash
pip install pyocd
python flash.py
```

### 串口 ISP

1. BOOT0 拨到 1
2. 按复位键
3. 使用 stm32loader 或 flash_v2.py 烧录
4. BOOT0 拨回 0，复位

## 串口读取

```python
import serial
ser = serial.Serial('COM6', 9600, timeout=3)
print(ser.read(100))
ser.close()
```

## 注意事项

- 寄存器访问全部使用宏定义，不依赖 .data 段初始化
- 启动文件 startup.o 必须放在链接顺序最前面 (向量表在 0x08000000)
- CRH 寄存器中 PA9=bits[7:4], PA10=bits[11:8]，写入时 0x4B 使 PA9=TX(0xB), PA10=RX(0x4)
- pyocd session.close() 后 MCU 可能停在 halt 状态，需手动复位
