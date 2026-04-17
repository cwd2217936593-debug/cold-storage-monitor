"""DHT11 温湿度传感器模拟器

模拟 DHT11 温湿度传感器的行为特性：
- 温度范围：0~50C（精度 ±2C）
- 湿度范围：20~90% RH（精度 ±5%）
- 单总线数字信号输出
- 读取周期建议 ≥2s（传感器响应较慢）

适用于：
- Windows 开发调试（真实 Adafruit-DHT / RPi.GPIO 无法在 Windows 安装）
- CI/CD 自动化测试
- 无硬件时的演示

真实硬件替换：只需将 simulators.DHT11Simulator 替换为 Adafruit_DHT，
接口设计已尽量对齐。
"""

import random
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional


class DHT11Simulator:
    """DHT11 温湿度传感器模拟器

    模拟 DHT11 的以下特性：
    - 测量精度：温度 ±2C，湿度 ±5% RH
    - 读取周期：建议 ≥2s（传感器需要充电时间）
    - 数据抖动：传感器有小幅随机波动
    - 偶尔读取失败：模拟真实总线的时序问题
    - 冷端漂移：低温环境下湿度读数偏高
    - 分辨率：温度 1C，湿度 1% RH

    使用示例::

        def on_data(data):
            print(f"温度={data['temperature']}C 湿度={data['humidity']}%")

        sim = DHT11Simulator(initial_temp=25.0, initial_humidity=60.0)
        sim.set_callback(on_data)
        sim.start()
        time.sleep(10)
        sim.stop()
    """

    def __init__(
        self,
        initial_temp: float = 25.0,
        initial_humidity: float = 60.0,
        interval: float = 2.0,
        failure_rate: float = 0.05,
    ):
        """初始化参数

        参数:
            initial_temp: 初始温度（C）
            initial_humidity: 初始湿度（% RH）
            interval: 读取间隔（秒），DHT11 建议 ≥2s
            failure_rate: 模拟读取失败的概率（0.0~1.0）
        """
        if not (0 <= failure_rate <= 1):
            raise ValueError("failure_rate must be between 0 and 1")

        self._interval = max(0.5, interval)
        self._failure_rate = failure_rate
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[Dict], None]] = None

        # 内部状态（连续变化，跟踪真实环境）
        self._env_temp = initial_temp
        self._env_humidity = initial_humidity
        self._last_temp: Optional[float] = None
        self._last_humidity: Optional[float] = None
        self._last_read_time = 0.0
        self._status = "normal"

    def set_callback(self, callback: Callable[[Dict], None]):
        self._callback = callback

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run_loop(self):
        while self._running:
            data = self._read_sensor()
            if self._callback:
                self._callback(data)
            time.sleep(self._interval)

    def _read_sensor(self) -> Dict:
        """模拟一次 DHT11 读取（拉低总线->传感器响应->40bit数据->校验）"""
        now = time.time()

        # 模拟读取失败（总线时序问题 / 校验失败）
        if random.random() < self._failure_rate:
            self._status = "read_error"
            return {
                "timestamp": datetime.now(),
                "temperature": self._last_temp,
                "humidity": self._last_humidity,
                "status": self._status,
                "error": "Checksum mismatch or timeout",
            }

        # 环境缓慢变化
        self._update_environment(now - self._last_read_time)

        # DHT11 实际读数 = 真值 + 量化误差 (±2C / ±5%) + 随机噪声
        temp_raw = self._env_temp + random.uniform(-2, 2)
        hum_raw = self._env_humidity + random.uniform(-5, 5)

        # 冷端漂移：温度 < 10C 时湿度读数偏高（真实 DHT11 特性）
        if self._env_temp < 10:
            hum_raw += (10 - self._env_temp) * 0.3

        # DHT11 分辨率为整数
        self._last_temp = round(max(0, min(50, temp_raw)))
        self._last_humidity = round(max(20, min(90, hum_raw)))
        self._last_read_time = now
        self._status = "ok"

        return {
            "timestamp": datetime.now(),
            "temperature": self._last_temp,
            "humidity": self._last_humidity,
            "status": self._status,
            "raw_temp": round(temp_raw, 1),
            "raw_humidity": round(hum_raw, 1),
        }

    def _update_environment(self, elapsed_sec: float):
        """模拟环境缓慢漂移（开门/关门、制冷机启停）"""
        if elapsed_sec <= 0:
            return

        # 温度 walk（每秒约 ±0.03C）
        self._env_temp += random.gauss(0, 0.03 * elapsed_sec)
        self._env_temp = max(-30, min(50, self._env_temp))

        # 湿度 walk（每秒约 ±0.1%）
        self._env_humidity += random.gauss(0, 0.1 * elapsed_sec)
        self._env_humidity = max(20, min(95, self._env_humidity))

        # 随机事件：模拟制冷机启停（温度突变 ±2~5C）
        if random.random() < 0.01 * elapsed_sec:
            if self._env_temp > -20:
                self._env_temp -= random.uniform(2, 5)
            else:
                self._env_temp += random.uniform(1, 3)

    def get_current_state(self) -> Dict:
        """获取最近一次读取结果"""
        return {
            "temperature": self._last_temp,
            "humidity": self._last_humidity,
            "status": self._status,
        }

    @property
    def env_temp(self) -> float:
        """当前模拟环境温度（精确浮点值）"""
        return self._env_temp

    @property
    def env_humidity(self) -> float:
        """当前模拟环境湿度（精确浮点值）"""
        return self._env_humidity


class DHT11Adapter:
    """
    兼容真实 Adafruit_DHT 接口的适配器，便于从模拟器迁移到真实硬件。

    使用示例（真实硬件上只需改一行）::

        # Windows 调试时:
        from simulators.dht11 import DHT11Simulator
        sensor = DHT11Simulator()

        # 真实树莓派上改为:
        import Adafruit_DHT
        sensor = Adafruit_DHT.DHT11
        pin = 4

        # 两种情况都可以这样调用:
        humidity, temperature = read_retry(sensor, pin)
    """
    DHT11 = "dht11"

    @staticmethod
    def read_retry(sensor, pin, retries=15, delay_seconds=2.0):
        """
        尝试读取传感器，重试直到成功或达到最大重试次数。

        返回: (humidity, temperature) 或 (None, None) 如果全部失败
        """
        for _ in range(retries):
            if isinstance(sensor, DHT11Simulator):
                data = sensor._read_sensor()
                if data["status"] == "ok":
                    return data["humidity"], data["temperature"]
            else:
                import Adafruit_DHT
                h, t = Adafruit_DHT.read_retry(Adafruit_DHT.DHT11, pin)
                if h is not None:
                    return h, t
            time.sleep(delay_seconds)
        return None, None


if __name__ == "__main__":
    print("=== DHT11 模拟器测试 ===")
    print("每 1 秒读取一次，共 10 次（冷库温度 -25C 场景）")

    sim = DHT11Simulator(
        initial_temp=-25.0,
        initial_humidity=55.0,
        interval=1.0,
        failure_rate=0.05,
    )

    def on_data(data):
        ts = data["timestamp"].strftime("%H:%M:%S")
        t = data["temperature"]
        h = data["humidity"]
        st = data["status"]
        err = data.get("error", "")
        env_t = f"env={sim.env_temp:.1f}C"
        env_h = f"env={sim.env_humidity:.1f}%"
        print(f"[{ts}] T={t}C {env_t} | H={h}% {env_h} | {st} {err}")

    sim.set_callback(on_data)
    sim.start()
    time.sleep(10)
    sim.stop()
    print("Done.")
