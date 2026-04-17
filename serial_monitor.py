"""
串口数据监控系统 - tkinter桌面版
支持 Windows / Linux / Mac
"""

import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import SERIAL_DEFAULTS, DEFAULT_FIELDS, list_serial_ports
from core.serial_reader import SerialReader, MultiPortReader, list_available_ports
from core.data_parser import ColdStorageDataParser, CustomizableParser
from core.alarm import AlarmManager, AlarmLevel, create_cold_storage_rules
from storage.data_storage import DataStorage
from simulators.cold_storage import ColdStorageSimulator
from simulators.custom import CustomSimulatorFactory


class SerialMonitorApp:
    """串口监控应用主类"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("串口数据监控系统 v1.0")
        self.root.geometry("1200x800")
        
        # 数据存储
        self.storage = DataStorage()
        
        # 报警管理
        self.alarm_manager = AlarmManager()
        self._setup_default_alarms()
        
        # 串口管理器
        self.port_reader = MultiPortReader()
        
        # 模拟器
        self.simulator: ColdStorageSimulator = None
        self.sim_enabled = tk.BooleanVar(value=False)
        
        # 当前数据
        self.current_data: dict = {}
        self.data_history: list = []
        self.max_history = 1000
        
        # 运行状态
        self.running = False
        
        # UI变量
        self.port_var = tk.StringVar()
        self.baudrate_var = tk.IntVar(value=115200)
        self._setup_ui()
        
        # 定期更新UI
        self._update_job = None
        
    def _setup_default_alarms(self):
        """设置默认报警规则"""
        for rule in create_cold_storage_rules():
            self.alarm_manager.add_rule(**rule)
            
        # 设置报警回调
        self.alarm_manager.set_on_alarm(self._on_alarm)
        
    def _setup_ui(self):
        """设置UI"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # 左侧控制面板
        left_frame = ttk.LabelFrame(main_frame, text="控制面板", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # 串口设置
        self._create_serial_frame(left_frame)
        
        # 模拟器设置
        self._create_simulator_frame(left_frame)
        
        # 操作按钮
        self._create_control_frame(left_frame)
        
        # 数据显示
        self._create_data_display(main_frame)
        
        # 报警显示
        self._create_alarm_frame(main_frame)
        
        # 右侧图表和历史
        right_frame = ttk.LabelFrame(main_frame, text="实时数据", padding="10")
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self._create_chart_area(right_frame)
        
        # 状态栏
        self._create_status_bar(main_frame)
        
    def _create_serial_frame(self, parent):
        """串口设置框架"""
        frame = ttk.LabelFrame(parent, text="串口设置", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))
        
        # 串口选择
        ttk.Label(frame, text="串口:").grid(row=0, column=0, sticky=tk.W)
        self.port_combo = ttk.Combobox(frame, textvariable=self.port_var, width=15)
        self.port_combo.grid(row=0, column=1, padx=5)
        
        refresh_btn = ttk.Button(frame, text="刷新", command=self._refresh_ports)
        refresh_btn.grid(row=0, column=2)
        
        # 波特率
        ttk.Label(frame, text="波特率:").grid(row=1, column=0, sticky=tk.W, pady=5)
        baudrate_combo = ttk.Combobox(
            frame, textvariable=self.baudrate_var, width=15,
            values=[9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
        )
        baudrate_combo.grid(row=1, column=1, padx=5, columnspan=2)
        
        self._refresh_ports()
        
    def _create_simulator_frame(self, parent):
        """模拟器设置框架"""
        frame = ttk.LabelFrame(parent, text="模拟器设置", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))
        
        sim_check = ttk.Checkbutton(
            frame, text="启用模拟器",
            variable=self.sim_enabled,
            command=self._toggle_simulator
        )
        sim_check.pack(anchor=tk.W)
        
        # 模拟器类型
        sim_frame = ttk.Frame(frame)
        sim_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(sim_frame, text="模式:").grid(row=0, column=0)
        self.sim_mode_var = tk.StringVar(value="cold_storage")
        sim_mode_combo = ttk.Combobox(
            sim_frame, textvariable=self.sim_mode_var, width=15,
            values=["cold_storage", "temperature", "pressure", "power", "environment"]
        )
        sim_mode_combo.grid(row=0, column=1, padx=5)
        
        # 数据格式
        ttk.Label(sim_frame, text="格式:").grid(row=1, column=0, pady=5)
        self.sim_format_var = tk.StringVar(value="key_value")
        format_combo = ttk.Combobox(
            sim_frame, textvariable=self.sim_format_var, width=15,
            values=["key_value", "csv", "json"]
        )
        format_combo.grid(row=1, column=1, padx=5)
        
        # 模拟间隔
        ttk.Label(sim_frame, text="间隔(s):").grid(row=2, column=0)
        self.sim_interval_var = tk.DoubleVar(value=1.0)
        ttk.Entry(sim_frame, textvariable=self.sim_interval_var, width=15).grid(row=2, column=1, padx=5)
        
    def _create_control_frame(self, parent):
        """控制按钮框架"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 10))
        
        self.connect_btn = ttk.Button(frame, text="连接", command=self._toggle_connection)
        self.connect_btn.pack(fill=tk.X, pady=2)
        
        self.start_btn = ttk.Button(frame, text="开始监控", command=self._toggle_monitoring, state=tk.DISABLED)
        self.start_btn.pack(fill=tk.X, pady=2)
        
        # 数据操作
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="保存CSV", command=self._save_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="保存Excel", command=self._save_excel).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="清空数据", command=self._clear_data).pack(side=tk.LEFT, padx=2)
        
    def _create_data_display(self, parent):
        """数据显示框架"""
        frame = ttk.LabelFrame(parent, text="当前数据", padding="10")
        frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        
        # 创建数据显示标签
        self.data_labels = {}
        fields = ['temperature', 'humidity', 'voltage', 'current', 'frost']
        units = ['°C', '%', 'V', 'A', '%']
        names = ['温度', '湿度', '电压', '电流', '结霜率']
        
        for i, (field, unit, name) in enumerate(zip(fields, units, names)):
            row = i // 2
            col = (i % 2) * 2
            
            ttk.Label(frame, text=f"{name}:", font=('Arial', 10, 'bold')).grid(
                row=row, column=col, sticky=tk.W, padx=5, pady=3
            )
            
            value_label = ttk.Label(frame, text="--", font=('Arial', 12))
            value_label.grid(row=row, column=col+1, sticky=tk.W, padx=5, pady=3)
            self.data_labels[field] = value_label
            
            unit_label = ttk.Label(frame, text=unit)
            unit_label.grid(row=row, column=col+2, sticky=tk.W)
            
        # 设备状态
        ttk.Label(frame, text="压缩机:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=3)
        self.comp_label = ttk.Label(frame, text="--", font=('Arial', 10))
        self.comp_label.grid(row=3, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(frame, text="风扇:").grid(row=3, column=2, sticky=tk.W, padx=5)
        self.fan_label = ttk.Label(frame, text="--")
        self.fan_label.grid(row=3, column=3, sticky=tk.W)
        
        ttk.Label(frame, text="门:").grid(row=4, column=0, sticky=tk.W, padx=5)
        self.door_label = ttk.Label(frame, text="--")
        self.door_label.grid(row=4, column=1, sticky=tk.W, padx=5)
        
        # 时间戳
        ttk.Label(frame, text="时间:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=3)
        self.time_label = ttk.Label(frame, text="--")
        self.time_label.grid(row=5, column=1, sticky=tk.W, padx=5)
        
    def _create_alarm_frame(self, parent):
        """报警显示框架"""
        frame = ttk.LabelFrame(parent, text="报警信息", padding="10")
        frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        
        # 报警列表
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.alarm_listbox = tk.Listbox(frame, height=8, yscrollcommand=scrollbar.set)
        self.alarm_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.alarm_listbox.yview)
        
        # 报警按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="确认报警", command=self._acknowledge_alarm).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="清除已确认", command=self._clear_acknowledged).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="查看历史", command=self._show_alarm_history).pack(side=tk.LEFT, padx=2)
        
    def _create_chart_area(self, parent):
        """图表区域"""
        # 创建画布用于简单绘图
        self.chart_canvas = tk.Canvas(parent, width=500, height=300, bg='white')
        self.chart_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 图表数据
        self.chart_data = {k: [] for k in ['temperature', 'humidity', 'voltage']}
        self.chart_colors = {
            'temperature': 'red',
            'humidity': 'blue',
            'voltage': 'green'
        }
        
        # 图例
        legend_frame = ttk.Frame(parent)
        legend_frame.pack(fill=tk.X)
        
        for field, color in self.chart_colors.items():
            frame = ttk.Frame(legend_frame)
            frame.pack(side=tk.LEFT, padx=10)
            tk.Canvas(frame, width=20, height=12, bg=color).pack(side=tk.LEFT)
            ttk.Label(frame, text=field).pack(side=tk.LEFT)
            
    def _create_status_bar(self, parent):
        """状态栏"""
        frame = ttk.Frame(parent)
        frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.status_label = ttk.Label(frame, text="就绪")
        self.status_label.pack(side=tk.LEFT)
        
        self.record_count_label = ttk.Label(frame, text="记录: 0")
        self.record_count_label.pack(side=tk.RIGHT)
        
    def _refresh_ports(self):
        """刷新串口列表"""
        ports = list_available_ports()
        port_list = [p['device'] for p in ports]
        self.port_combo['values'] = port_list
        if port_list:
            self.port_combo.current(0)
            
    def _toggle_simulator(self):
        """切换模拟器"""
        if self.sim_enabled.get():
            mode = self.sim_mode_var.get()
            interval = self.sim_interval_var.get()
            data_format = self.sim_format_var.get()
            
            self.simulator = CustomSimulatorFactory.create(
                mode, interval=interval, data_format=data_format
            )
            self.simulator.set_callback(self._on_simulator_data)
            self.simulator.start()
            self.status_label.config(text="模拟器运行中")
            self.connect_btn.config(state=tk.DISABLED)
        else:
            if self.simulator:
                self.simulator.stop()
                self.simulator = None
            self.connect_btn.config(state=tk.NORMAL)
            self.status_label.config(text="就绪")
            
    def _toggle_connection(self):
        """切换连接状态"""
        if self.connect_btn.cget('text') == "连接":
            self._connect()
        else:
            self._disconnect()
            
    def _connect(self):
        """连接串口"""
        port = self.port_var.get()
        if not port:
            messagebox.showwarning("警告", "请选择串口")
            return
            
        try:
            reader = self.port_reader.add_port(
                "main", port, self.baudrate_var.get(),
                parser=ColdStorageDataParser()
            )
            reader.connect()
            reader.set_on_data(self._on_serial_data)
            reader.set_on_error(self._on_error)
            reader.start()
            
            self.connect_btn.config(text="断开")
            self.start_btn.config(state=tk.NORMAL)
            self.status_label.config(text=f"已连接 {port}")
            
        except Exception as e:
            messagebox.showerror("连接错误", str(e))
            
    def _disconnect(self):
        """断开连接"""
        self.port_reader.stop_all()
        self.connect_btn.config(text="连接")
        self.start_btn.config(state=tk.DISABLED)
        self.status_label.config(text="已断开")
        
    def _toggle_monitoring(self):
        """切换监控状态"""
        if self.start_btn.cget('text') == "开始监控":
            self.running = True
            self.start_btn.config(text="停止监控")
            self.storage.start_auto_save()
            self._start_ui_update()
        else:
            self.running = False
            self.start_btn.config(text="开始监控")
            self.storage.stop_auto_save()
            self._stop_ui_update()
            
    def _on_serial_data(self, data: dict):
        """串口数据回调"""
        self._process_data(data)
        
    def _on_simulator_data(self, data: dict):
        """模拟器数据回调"""
        self._process_data(data)
        
    def _process_data(self, data: dict):
        """处理数据"""
        self.current_data = data
        self.storage.add_record(data)
        
        # 检查报警
        self.alarm_manager.check_data(data)
        
        # 更新历史
        self.data_history.append(data)
        if len(self.data_history) > self.max_history:
            self.data_history = self.data_history[-self.max_history:]
            
    def _on_alarm(self, alarm):
        """报警回调"""
        self.alarm_listbox.insert(0, f"[{alarm.level.value}] {alarm.message}")
        self.alarm_listbox.itemconfig(0, fg=self._get_alarm_color(alarm.level))
        
    def _get_alarm_color(self, level: AlarmLevel) -> str:
        """获取报警颜色"""
        colors = {
            AlarmLevel.INFO: 'blue',
            AlarmLevel.WARNING: 'orange',
            AlarmLevel.ERROR: 'red',
            AlarmLevel.CRITICAL: 'purple'
        }
        return colors.get(level, 'black')
        
    def _on_error(self, error: Exception):
        """错误回调"""
        self.status_label.config(text=f"错误: {error}")
        
    def _start_ui_update(self):
        """开始UI更新"""
        self._update_ui()
        
    def _stop_ui_update(self):
        """停止UI更新"""
        if self._update_job:
            self.root.after_cancel(self._update_job)
            self._update_job = None
            
    def _update_ui(self):
        """更新UI"""
        if not self.running:
            return
            
        # 更新数据显示
        for field, label in self.data_labels.items():
            if field in self.current_data:
                value = self.current_data[field]
                if isinstance(value, (int, float)):
                    label.config(text=f"{value:.2f}")
                    
        # 更新设备状态
        if 'comp' in self.current_data:
            self.comp_label.config(text="开启" if self.current_data['comp'] else "关闭")
        if 'fan' in self.current_data:
            self.fan_label.config(text="开启" if self.current_data['fan'] else "关闭")
        if 'door' in self.current_data:
            self.door_label.config(text="开启" if self.current_data['door'] else "关闭")
            
        # 更新时间
        if 'timestamp' in self.current_data:
            ts = self.current_data['timestamp']
            if isinstance(ts, str):
                self.time_label.config(text=ts)
            elif hasattr(ts, 'strftime'):
                self.time_label.config(text=ts.strftime("%H:%M:%S"))
                
        # 更新图表
        self._update_chart()
        
        # 更新记录数
        count = self.storage.get_memory_usage()
        self.record_count_label.config(text=f"记录: {count}")
        
        # 继续更新
        self._update_job = self.root.after(100, self._update_ui)
        
    def _update_chart(self):
        """更新图表"""
        self.chart_canvas.delete('all')
        
        # 添加数据点
        for field, values in self.chart_data.items():
            if field in self.current_data:
                values.append(self.current_data[field])
                if len(values) > 100:
                    values.pop(0)
                    
        # 绘制图表
        width = self.chart_canvas.winfo_width()
        height = self.chart_canvas.winfo_height()
        
        if width <= 1:
            width = 500
        if height <= 1:
            height = 300
            
        # 绘制网格
        for i in range(5):
            y = height * i / 4
            self.chart_canvas.create_line(0, y, width, y, fill='lightgray', dash=(2, 2))
            
        # 绘制数据线
        for field, color in self.chart_colors.items():
            values = self.chart_data[field]
            if len(values) > 1:
                points = []
                for i, v in enumerate(values):
                    x = width * i / (len(values) - 1) if len(values) > 1 else width / 2
                    y = height - (v - (-50)) / 150 * height  # 归一化
                    y = max(0, min(height, y))
                    points.append((x, y))
                    
                for i in range(len(points) - 1):
                    self.chart_canvas.create_line(
                        points[i][0], points[i][1],
                        points[i+1][0], points[i+1][1],
                        fill=color, width=2
                    )
                    
    def _save_csv(self):
        """保存CSV"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")]
        )
        if filepath:
            path = self.storage.save_to_csv(filepath)
            messagebox.showinfo("保存成功", f"已保存到: {path}")
            
    def _save_excel(self):
        """保存Excel"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")]
        )
        if filepath:
            path = self.storage.save_to_excel(filepath)
            messagebox.showinfo("保存成功", f"已保存到: {path}")
            
    def _clear_data(self):
        """清空数据"""
        if messagebox.askyesno("确认", "确定清空所有数据?"):
            self.storage.clear()
            self.data_history.clear()
            self.current_data.clear()
            for label in self.data_labels.values():
                label.config(text="--")
            self.record_count_label.config(text="记录: 0")
            
    def _acknowledge_alarm(self):
        """确认报警"""
        selection = self.alarm_listbox.curselection()
        if selection:
            alarms = self.alarm_manager.get_active_alarms()
            if selection[0] < len(alarms):
                self.alarm_manager.acknowledge_alarm(alarms[selection[0]]['id'])
                self.alarm_listbox.delete(selection[0])
                
    def _clear_acknowledged(self):
        """清除已确认的报警"""
        self.alarm_manager.clear_alarm.__func__(self.alarm_manager, '')
        
    def _show_alarm_history(self):
        """显示报警历史"""
        history = self.alarm_manager.get_alarm_history(50)
        if history:
            text = "\n".join([f"{a['timestamp']} [{a['level']}] {a['message']}" for a in history])
        else:
            text = "无历史报警"
            
        messagebox.showinfo("报警历史", text)
        
    def run(self):
        """运行应用"""
        self.root.mainloop()


def main():
    app = SerialMonitorApp()
    app.run()


if __name__ == "__main__":
    main()
