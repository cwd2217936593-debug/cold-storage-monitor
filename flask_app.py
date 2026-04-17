"""
串口数据监控系统 - Flask Web版本
轻量级替代方案，兼容所有环境
"""

import sys
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from io import StringIO

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from flask import Flask, render_template_string, Response, request, jsonify
import pandas as pd

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import SERIAL_DEFAULTS, DEFAULT_FIELDS
from core.serial_reader import SerialReader, MultiPortReader, list_available_ports
from core.data_parser import ColdStorageDataParser, CustomizableParser
from core.alarm import AlarmManager, AlarmLevel, create_cold_storage_rules
from storage.data_storage import DataStorage
from simulators.cold_storage import ColdStorageSimulator
from simulators.custom import CustomSimulatorFactory
from ai_analysis import predict_frost, load_model, get_feature_importance
from simulators.custom import CustomSimulatorFactory


# Flask应用
app = Flask(__name__)

# 全局状态
monitor_state = {
    'running': False,
    'simulator': None,
    'port_reader': None,
    'alarm_manager': AlarmManager(),
    'storage': DataStorage(),
    'data_buffer': [],
    'max_buffer': 1000,
    'data_df': pd.DataFrame(columns=['timestamp', 'temperature', 'humidity', 'voltage', 
                                       'current', 'power', 'frost', 'comp', 'fan', 'door']),
    'history_data': [],   # 用于AI分析的历史数据（列表形式）
    'max_history': 120,   # 最多保留120分钟历史
    'ai_result': None,    # 最新AI预测结果
}

# 设置默认报警规则
for rule in create_cold_storage_rules():
    monitor_state['alarm_manager'].add_rule(**rule)


def check_data(data):
    """数据回调"""
    if monitor_state['running']:
        ts = data.get('timestamp', datetime.now().isoformat())
        
        # 添加到DataFrame
        new_row = pd.DataFrame([data])
        new_row['timestamp'] = pd.to_datetime(new_row['timestamp'])
        monitor_state['data_df'] = pd.concat([monitor_state['data_df'], new_row], ignore_index=True)
        
        # 限制数据量
        if len(monitor_state['data_df']) > monitor_state['max_buffer']:
            monitor_state['data_df'] = monitor_state['data_df'].tail(monitor_state['max_buffer'])
        
        # 维护历史数据（用于AI分析）
        monitor_state['history_data'].append(data)
        if len(monitor_state['history_data']) > monitor_state['max_history']:
            monitor_state['history_data'] = monitor_state['history_data'][-monitor_state['max_history']:]
        
        # 存储
        monitor_state['storage'].add_record(data)
        
        # 报警检查
        monitor_state['alarm_manager'].check_data(data)
        
        # AI趋势分析（每5条数据跑一次，避免性能开销）
        if len(monitor_state['history_data']) >= 5 and len(monitor_state['data_df']) % 5 == 0:
            monitor_state['ai_result'] = predict_frost(data, monitor_state['history_data'])


# HTML模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>串口数据监控系统</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
        }
        .header {
            background: rgba(0,0,0,0.3);
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .header h1 { font-size: 1.5rem; color: #4ecdc4; }
        .header .status { display: flex; gap: 20px; }
        .status-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 15px;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            font-size: 0.9rem;
        }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; }
        .dot-green { background: #28a745; box-shadow: 0 0 10px #28a745; }
        .dot-red { background: #dc3545; box-shadow: 0 0 10px #dc3545; }
        .dot-yellow { background: #ffc107; box-shadow: 0 0 10px #ffc107; }
        
        .container { display: flex; min-height: calc(100vh - 70px); }
        
        /* 侧边栏 */
        .sidebar {
            width: 280px;
            background: rgba(0,0,0,0.2);
            padding: 20px;
            border-right: 1px solid rgba(255,255,255,0.1);
        }
        .panel {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .panel h3 {
            font-size: 1rem;
            margin-bottom: 12px;
            color: #4ecdc4;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .control-btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 8px;
        }
        .btn-start { background: #28a745; color: white; }
        .btn-stop { background: #dc3545; color: white; }
        .btn-sim { background: #17a2b8; color: white; }
        .btn-save { background: #6c757d; color: white; }
        .control-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        .control-btn:active { transform: translateY(0); }
        
        .form-group { margin-bottom: 12px; }
        .form-group label { display: block; font-size: 0.85rem; margin-bottom: 5px; color: #aaa; }
        .form-group select, .form-group input {
            width: 100%;
            padding: 8px;
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 5px;
            color: white;
            font-size: 0.9rem;
        }
        
        /* 主内容 */
        .main { flex: 1; padding: 20px; }
        
        /* 指标卡片 */
        .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .metric-card {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            transition: all 0.3s;
        }
        .metric-card:hover { background: rgba(255,255,255,0.1); transform: translateY(-3px); }
        .metric-value { font-size: 2rem; font-weight: bold; margin: 10px 0; }
        .metric-label { font-size: 0.85rem; color: #aaa; }
        .metric-card .icon { font-size: 2rem; }
        .temp { color: #ff6b6b; }
        .hum { color: #4ecdc4; }
        .volt { color: #45b7d1; }
        .frost { color: #a8e6cf; }
        .alarm { color: #ffc107; }
        .records { color: #dda0dd; }
        
        /* 图表 */
        .chart-container {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .chart-header h3 { color: #4ecdc4; }
        
        /* 数据表格 */
        .data-table-container {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 20px;
            overflow-x: auto;
        }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { color: #4ecdc4; font-weight: 600; }
        tr:hover { background: rgba(255,255,255,0.05); }
        
        /* 报警面板 */
        .alarm-panel {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .alarm-item {
            padding: 10px 15px;
            border-radius: 5px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .alarm-critical { background: rgba(220,53,69,0.3); border-left: 3px solid #dc3545; }
        .alarm-error { background: rgba(255,127,14,0.3); border-left: 3px solid #ff7f0e; }
        .alarm-warning { background: rgba(255,193,7,0.3); border-left: 3px solid #ffc107; }
        .alarm-info { background: rgba(23,162,184,0.3); border-left: 3px solid #17a2b8; }
        .no-alarm { color: #28a745; padding: 15px; text-align: center; }
        
        /* 设备状态 */
        .device-status {
            display: flex;
            gap: 15px;
            margin-top: 10px;
        }
        .device-item {
            flex: 1;
            padding: 10px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            text-align: center;
        }
        .device-on { color: #28a745; }
        .device-off { color: #dc3545; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📡 串口数据监控系统</h1>
        <div class="status">
            <div class="status-item">
                <div class="status-dot {{ 'dot-green' if running else 'dot-red' }}"></div>
                <span>{{ '运行中' if running else '已停止' }}</span>
            </div>
            <div class="status-item">
                <div class="status-dot {{ 'dot-green' if simulator else 'dot-yellow' }}"></div>
                <span>{{ '模拟器开' if simulator else '模拟器关' }}</span>
            </div>
            <div class="status-item">
                <span>📊 {{ record_count }} 条记录</span>
            </div>
        </div>
    </div>
    
    <div class="container">
        <div class="sidebar">
            <div class="panel">
                <h3>🎭 模拟器</h3>
                <div class="form-group">
                    <label>模式</label>
                    <select id="simMode">
                        <option value="cold_storage">🧊 冷库</option>
                        <option value="temperature">🌡️ 温度</option>
                        <option value="pressure">📊 压力</option>
                        <option value="power">⚡ 功率</option>
                        <option value="environment">🌍 环境</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>数据间隔 (秒)</label>
                    <input type="number" id="simInterval" value="1.0" step="0.1" min="0.1" max="10">
                </div>
                <div class="form-group">
                    <label>数据格式</label>
                    <select id="simFormat">
                        <option value="key_value">键值对 (T:25.5)</option>
                        <option value="json">JSON</option>
                        <option value="csv">CSV</option>
                    </select>
                </div>
                <button class="control-btn btn-sim" onclick="toggleSimulator()">
                    {{ '🔴 关闭模拟器' if simulator else '🟢 启用模拟器' }}
                </button>
            </div>
            
            <div class="panel">
                <h3>▶️ 监控控制</h3>
                <button class="control-btn {{ 'btn-stop' if running else 'btn-start' }}" onclick="toggleMonitor()">
                    {{ '⏸️ 停止监控' if running else '▶️ 开始监控' }}
                </button>
            </div>
            
            <div class="panel">
                <h3>💾 数据操作</h3>
                <button class="control-btn btn-save" onclick="saveCSV()">📥 导出CSV</button>
                <button class="control-btn btn-save" onclick="saveExcel()">📊 导出Excel</button>
                <button class="control-btn btn-save" onclick="clearData()">🗑️ 清空数据</button>
            </div>
        </div>
        
        <div class="main">
            <div class="metrics">
                <div class="metric-card">
                    <div class="icon temp">🌡️</div>
                    <div class="metric-value temp" id="tempValue">{{ '%.1f'|format(current_data.get('temperature', 0)) }}°C</div>
                    <div class="metric-label">温度</div>
                </div>
                <div class="metric-card">
                    <div class="icon hum">💧</div>
                    <div class="metric-value hum" id="humValue">{{ '%.1f'|format(current_data.get('humidity', 0)) }}%</div>
                    <div class="metric-label">湿度</div>
                </div>
                <div class="metric-card">
                    <div class="icon volt">⚡</div>
                    <div class="metric-value volt" id="voltValue">{{ '%.1f'|format(current_data.get('voltage', 0)) }}V</div>
                    <div class="metric-label">电压</div>
                </div>
                <div class="metric-card">
                    <div class="icon frost">❄️</div>
                    <div class="metric-value frost" id="frostValue">{{ '%.1f'|format(current_data.get('frost', 0)) }}%</div>
                    <div class="metric-label">结霜率</div>
                </div>
                <div class="metric-card">
                    <div class="icon alarm">⚠️</div>
                    <div class="metric-value alarm">{{ active_alarm_count }}</div>
                    <div class="metric-label">活跃报警</div>
                </div>
                <div class="metric-card">
                    <div class="icon records">📊</div>
                    <div class="metric-value records">{{ record_count }}</div>
                    <div class="metric-label">总记录数</div>
                </div>
            </div>
            
            <div class="alarm-panel">
                <h3 style="color:#4ecdc4; margin-bottom:15px;">⚠️ 报警状态</h3>
                {% if active_alarms %}
                    {% for alarm in active_alarms %}
                        <div class="alarm-item alarm-{{ alarm.level }}">
                            <span>🔔 {{ alarm.message }}</span>
                            <small>{{ alarm.timestamp }}</small>
                        </div>
                    {% endfor %}
                {% else %}
                    <div class="no-alarm">✅ 当前无活跃报警</div>
                {% endif %}
            </div>
            
            <!-- AI趋势分析 -->
            {% if ai_result and ai_result.model_ready %}
            <div class="alarm-panel" style="border: 2px solid {{ ai_result.defrost_color }};">
                <h3 style="color:{{ ai_result.defrost_color }}; margin-bottom:15px;">
                    🧠 AI趋势分析
                    <span style="font-size:0.8rem; color:#aaa; margin-left:10px;">
                        置信度: {% if ai_result.confidence == 'high' %}🟢 高{% elif ai_result.confidence == 'medium' %}🟡 中{% else %}🔴 低{% endif %}
                        (需要数据积累后提升)
                    </span>
                </h3>
                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:15px;">
                    <div style="text-align:center; padding:15px; background:rgba(0,0,0,0.2); border-radius:10px;">
                        <div style="font-size:0.9rem; color:#aaa; margin-bottom:5px;">预测结霜率</div>
                        <div style="font-size:2.5rem; font-weight:bold; color:#a8e6cf;">{{ ai_result.frost_pred }}%</div>
                    </div>
                    <div style="text-align:center; padding:15px; background:rgba(0,0,0,0.2); border-radius:10px;">
                        <div style="font-size:0.9rem; color:#aaa; margin-bottom:5px;">实际结霜率</div>
                        <div style="font-size:2.5rem; font-weight:bold; color:#ff6b6b;">{{ ai_result.frost_actual }}%</div>
                    </div>
                    <div style="text-align:center; padding:15px; background:rgba(0,0,0,0.2); border-radius:10px;">
                        <div style="font-size:0.9rem; color:#aaa; margin-bottom:5px;">趋势判断</div>
                        <div style="font-size:1.5rem;">{{ ai_result.trend_icon }} {{ ai_result.trend_desc }}</div>
                        <div style="font-size:0.8rem; color:#aaa; margin-top:5px;">变化率: {{ ai_result.change_rate }}%/h</div>
                    </div>
                    <div style="text-align:center; padding:15px; background:rgba(0,0,0,0.2); border-radius:10px; border: 2px solid {{ ai_result.defrost_color }};">
                        <div style="font-size:0.9rem; color:#aaa; margin-bottom:5px;">除霜建议</div>
                        <div style="font-size:1.5rem; font-weight:bold; color:{{ ai_result.defrost_color }};">
                            {{ ai_result.defrost_icon }} {{ ai_result.defrost_advice }}
                        </div>
                    </div>
                </div>
                <div style="margin-top:12px; padding:10px; background:rgba(78,205,196,0.1); border-radius:8px;">
                    <span style="color:#4ecdc4;">🔮 未来趋势:</span> {{ ai_result.future_trend }}
                </div>
            </div>
            {% else %}
            <div class="alarm-panel">
                <h3 style="color:#888; margin-bottom:15px;">🧠 AI趋势分析</h3>
                <div style="text-align:center; padding:30px; color:#888;">
                    <div style="font-size:2rem; margin-bottom:10px;">🤖</div>
                    <div>启动监控并收集数据后，AI分析将自动开启</div>
                    <div style="font-size:0.85rem; margin-top:8px;">
                        需要至少5条历史数据，置信度随数据积累提升
                    </div>
                </div>
            </div>
            {% endif %}
            
            <div class="chart-container">
                <div class="chart-header">
                    <h3>📈 实时趋势</h3>
                </div>
                <div id="chart" style="height:400px;"></div>
            </div>
            
            <div class="data-table-container">
                <h3 style="color:#4ecdc4; margin-bottom:15px;">📋 最新数据</h3>
                <table>
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>温度(°C)</th>
                            <th>湿度(%)</th>
                            <th>电压(V)</th>
                            <th>电流(A)</th>
                            <th>功率(kW)</th>
                            <th>结霜率(%)</th>
                            <th>压缩机</th>
                            <th>风扇</th>
                            <th>门</th>
                        </tr>
                    </thead>
                    <tbody id="dataTableBody">
                        {% for _, row in data_table.iterrows() %}
                        <tr>
                            <td>{{ row.timestamp.strftime('%H:%M:%S') if row.timestamp else '--' }}</td>
                            <td>{{ '%.2f'|format(row.temperature) if pd.notna(row.temperature) else '--' }}</td>
                            <td>{{ '%.2f'|format(row.humidity) if pd.notna(row.humidity) else '--' }}</td>
                            <td>{{ '%.2f'|format(row.voltage) if pd.notna(row.voltage) else '--' }}</td>
                            <td>{{ '%.2f'|format(row.current) if pd.notna(row.current) else '--' }}</td>
                            <td>{{ '%.2f'|format(row.power) if pd.notna(row.power) else '--' }}</td>
                            <td>{{ '%.2f'|format(row.frost) if pd.notna(row.frost) else '--' }}</td>
                            <td>{{ '🟢' if row.get('comp', 0) else '🔴' }}</td>
                            <td>{{ '🟢' if row.get('fan', 0) else '🔴' }}</td>
                            <td>{{ '🟡' if row.get('door', 0) else '🟢' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <script>
        // 自动刷新
        setTimeout(() => location.reload(), 2000);
        
        // 控制函数
        function toggleMonitor() {
            fetch('/api/toggle', {method: 'POST'}).then(() => location.reload());
        }
        
        function toggleSimulator() {
            const mode = document.getElementById('simMode').value;
            const interval = document.getElementById('simInterval').value;
            const format = document.getElementById('simFormat').value;
            fetch('/api/simulator', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode, interval: parseFloat(interval), format})
            }).then(() => location.reload());
        }
        
        function saveCSV() {
            window.location.href = '/api/export/csv';
        }
        
        function saveExcel() {
            window.location.href = '/api/export/excel';
        }
        
        function clearData() {
            if (confirm('确定清空所有数据?')) {
                fetch('/api/clear', {method: 'POST'}).then(() => location.reload());
            }
        }
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """主页"""
    active_alarms = monitor_state['alarm_manager'].get_active_alarms()
    active_alarm_count = len(active_alarms)
    record_count = len(monitor_state['data_df'])
    running = monitor_state['running']
    simulator = monitor_state['simulator'] is not None
    
    # 当前数据
    if len(monitor_state['data_df']) > 0:
        current_data = monitor_state['data_df'].iloc[-1].to_dict()
    else:
        current_data = {}
    
    # 数据表格（最新20条）
    data_table = monitor_state['data_df'].tail(20)
    
    return render_template_string(
        HTML_TEMPLATE,
        running=running,
        simulator=simulator,
        record_count=record_count,
        active_alarm_count=active_alarm_count,
        active_alarms=active_alarms,
        current_data=current_data,
        data_table=data_table,
        ai_result=monitor_state.get('ai_result'),
        pd=pd
    )


@app.route('/api/toggle', methods=['POST'])
def api_toggle():
    """切换监控状态"""
    monitor_state['running'] = not monitor_state['running']
    
    if monitor_state['running']:
        if monitor_state['simulator']:
            monitor_state['simulator'].start()
        monitor_state['storage'].start_auto_save()
    else:
        if monitor_state['simulator']:
            monitor_state['simulator'].stop()
        monitor_state['storage'].stop_auto_save()
    
    return jsonify({'running': monitor_state['running']})


@app.route('/api/simulator', methods=['POST'])
def api_simulator():
    """配置模拟器"""
    data = request.json
    
    # 停止现有模拟器
    if monitor_state['simulator']:
        monitor_state['simulator'].stop()
        monitor_state['simulator'] = None
    
    # 创建新模拟器
    mode = data.get('mode', 'cold_storage')
    interval = data.get('interval', 1.0)
    fmt = data.get('format', 'key_value')
    
    simulator = CustomSimulatorFactory.create(mode, interval=interval, data_format=fmt)
    simulator.set_callback(check_data)
    simulator.start()
    monitor_state['simulator'] = simulator
    
    return jsonify({'success': True})


@app.route('/api/export/csv')
def api_export_csv():
    """导出CSV"""
    if len(monitor_state['data_df']) == 0:
        return "No data", 400
    
    csv_buffer = StringIO()
    monitor_state['data_df'].to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        csv_buffer.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=data_{timestamp}.csv'}
    )


@app.route('/api/export/excel')
def api_export_excel():
    """导出Excel"""
    if len(monitor_state['data_df']) == 0:
        return "No data", 400
    
    from io import BytesIO
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        monitor_state['data_df'].to_excel(writer, index=False, sheet_name='数据')
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=data_{timestamp}.xlsx'}
    )


@app.route('/api/clear', methods=['POST'])
def api_clear():
    """清空数据"""
    monitor_state['data_df'] = pd.DataFrame(columns=monitor_state['data_df'].columns)
    monitor_state['history_data'] = []
    monitor_state['ai_result'] = None
    monitor_state['storage'].clear()
    return jsonify({'success': True})


@app.route('/api/status')
def api_status():
    """获取状态"""
    return jsonify({
        'running': monitor_state['running'],
        'simulator': monitor_state['simulator'] is not None,
        'record_count': len(monitor_state['data_df']),
        'alarm_count': len(monitor_state['alarm_manager'].get_active_alarms())
    })


if __name__ == '__main__':
    print("=" * 50)
    print("串口数据监控系统 - Flask Web版")
    print("=" * 50)
    print("访问地址: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
