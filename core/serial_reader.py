"""
串口读取核心模块 - 跨平台支持
"""

import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import serial
from serial.tools.list_ports import comports

from .data_parser import ColdStorageDataParser, CustomizableParser, DataParser


class SerialReader:
    """串口读取器"""
    
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        bytesize: int = 8,
        parity: str = 'N',
        stopbits: int = 1,
        timeout: float = 1.0,
        parser: Optional[DataParser] = None
    ):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        
        # 解析器
        self.parser = parser or ColdStorageDataParser()
        
        # 状态
        self._serial: Optional[serial.Serial] = None
        self._reading_thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        
        # 数据队列
        self._data_queue: queue.Queue = queue.Queue()
        
        # 回调函数
        self._on_data_callback: Optional[Callable] = None
        self._on_error_callback: Optional[Callable] = None
        self._on_connect_callback: Optional[Callable] = None
        self._on_disconnect_callback: Optional[Callable] = None
        
        # 统计
        self._stats = {
            'bytes_received': 0,
            'frames_received': 0,
            'frames_valid': 0,
            'frames_invalid': 0,
            'errors': 0,
            'start_time': None,
            'last_data_time': None,
        }
        
        # 锁
        self._lock = threading.Lock()
        
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
        
    @property
    def is_running(self) -> bool:
        """是否正在读取"""
        return self._running
        
    def set_on_data(self, callback: Callable[[Dict], None]):
        """设置数据回调"""
        self._on_data_callback = callback
        
    def set_on_error(self, callback: Callable[[Exception], None]):
        """设置错误回调"""
        self._on_error_callback = callback
        
    def set_on_connect(self, callback: Callable[[], None]):
        """设置连接回调"""
        self._on_connect_callback = callback
        
    def set_on_disconnect(self, callback: Callable[[], None]):
        """设置断开回调"""
        self._on_disconnect_callback = callback
        
    def connect(self) -> bool:
        """连接串口"""
        if self._connected:
            return True
            
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
            )
            
            # 清空缓冲区
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            
            self._connected = True
            self._stats['start_time'] = datetime.now()
            
            if self._on_connect_callback:
                self._on_connect_callback()
                
            return True
            
        except Exception as e:
            self._connected = False
            if self._on_error_callback:
                self._on_error_callback(e)
            raise
            
    def disconnect(self):
        """断开连接"""
        self.stop()
        
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
            self._connected = False
            
        if self._on_disconnect_callback:
            self._on_disconnect_callback()
            
    def start(self):
        """开始读取"""
        if self._running:
            return
            
        if not self._connected:
            self.connect()
            
        self._running = True
        self._reading_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reading_thread.start()
        
    def stop(self):
        """停止读取"""
        self._running = False
        
        if self._reading_thread:
            self._reading_thread.join(timeout=2)
            self._reading_thread = None
            
    def _read_loop(self):
        """读取循环"""
        buffer = ""
        
        while self._running and self._connected:
            try:
                if self._serial and self._serial.in_waiting > 0:
                    # 读取数据
                    data = self._serial.read(self._serial.in_waiting)
                    self._stats['bytes_received'] += len(data)
                    
                    try:
                        text = data.decode('utf-8', errors='replace')
                    except:
                        text = data.decode('gbk', errors='replace')
                    
                    buffer += text
                    self._stats['last_data_time'] = datetime.now()
                    
                    # 处理缓冲数据 - 按行分割
                    while '\n' in buffer or '\r' in buffer:
                        # 找到行尾
                        if '\r\n' in buffer:
                            line, buffer = buffer.split('\r\n', 1)
                        elif '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                        elif '\r' in buffer:
                            line, buffer = buffer.split('\r', 1)
                        else:
                            break
                            
                        line = line.strip()
                        if not line:
                            continue
                            
                        self._stats['frames_received'] += 1
                        
                        # 解析数据
                        parsed = self.parser.parse(line)
                        
                        if parsed:
                            self._stats['frames_valid'] += 1
                            self._data_queue.put(parsed)
                            
                            if self._on_data_callback:
                                self._on_data_callback(parsed)
                        else:
                            self._stats['frames_invalid'] += 1
                            
                else:
                    # 没有数据时短暂休眠
                    time.sleep(0.01)
                    
            except Exception as e:
                self._stats['errors'] += 1
                if self._on_error_callback:
                    self._on_error_callback(e)
                time.sleep(0.1)
                
    def get_data(self, timeout: float = 0.1) -> Optional[Dict]:
        """获取一条数据"""
        try:
            return self._data_queue.get(timeout=timeout)
        except queue.Empty:
            return None
            
    def get_all_data(self) -> List[Dict]:
        """获取所有待处理数据"""
        data_list = []
        while True:
            try:
                data = self._data_queue.get_nowait()
                data_list.append(data)
            except queue.Empty:
                break
        return data_list
        
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            return self._stats.copy()
            
    def clear_stats(self):
        """清空统计"""
        with self._lock:
            self._stats = {
                'bytes_received': 0,
                'frames_received': 0,
                'frames_valid': 0,
                'frames_invalid': 0,
                'errors': 0,
                'start_time': datetime.now(),
                'last_data_time': None,
            }
            
    def __enter__(self):
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        

class MultiPortReader:
    """多串口读取管理器"""
    
    def __init__(self):
        self._readers: Dict[str, SerialReader] = {}
        self._lock = threading.Lock()
        
    def add_port(
        self,
        name: str,
        port: str,
        baudrate: int = 115200,
        parser: Optional[DataParser] = None
    ) -> SerialReader:
        """添加一个串口"""
        with self._lock:
            if name in self._readers:
                self._readers[name].disconnect()
                
            reader = SerialReader(port, baudrate, parser=parser)
            self._readers[name] = reader
            return reader
            
    def remove_port(self, name: str):
        """移除一个串口"""
        with self._lock:
            if name in self._readers:
                self._readers[name].disconnect()
                del self._readers[name]
                
    def get_reader(self, name: str) -> Optional[SerialReader]:
        """获取指定串口读取器"""
        return self._readers.get(name)
        
    def start_all(self):
        """启动所有串口"""
        with self._lock:
            for reader in self._readers.values():
                reader.start()
                
    def stop_all(self):
        """停止所有串口"""
        with self._lock:
            for reader in self._readers.values():
                reader.stop()
                
    def get_all_readers(self) -> Dict[str, SerialReader]:
        """获取所有读取器"""
        return self._readers.copy()
        
    def list_ports(self) -> List[str]:
        """列出所有已添加的端口"""
        return list(self._readers.keys())
        

def list_available_ports() -> List[Dict]:
    """列出所有可用的串口"""
    ports = []
    for port in comports():
        ports.append({
            'device': port.device,
            'name': port.name,
            'description': port.description,
            'hwid': port.hwid,
        })
    return ports
