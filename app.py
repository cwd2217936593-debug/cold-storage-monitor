# -*- coding: utf-8 -*-
"""
串口监控系统 - 独立桌面应用
Python HTTP服务器 + 纯HTML前端，零依赖Flask/PyInstaller友好
"""
import os
import sys
import json
import threading
import time
import webbrowser
import hashlib
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ============================================================
# 路径设置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ============================================================
# 尝试导入可选依赖，缺失时用内置替代
# ============================================================
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False


# ============================================================
# 全局状态
# ============================================================
class MonitorState:
    def __init__(self):
        self.running = False
        self.simulator = None
        self.alarms = []
        self.data_history = []
        self.max_history = 200
        self.ai_model = None
        self.ai_loaded = False
        self.current_data = {}
        self.last_alarm_time = {}
        self.record_count = 0
        self.start_time = None

state = MonitorState()

# 模拟器实现（内置）
class ColdStorageSimulator:
    def __init__(self, interval=1.0):
        self.interval = interval
        self.running = False
        self.thread = None
        self.t = 0
        self.comp = 1
        self.fan = 1
        self.door = 0
        self.frost = 0.0
        self.event_mode = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _loop(self):
        while self.running:
            self.t += 1
            data = self._generate_data()
            if state.running:
                self._on_data(data)
            time.sleep(self.interval)

    def _generate_data(self):
        # 周期性结霜模拟 (0→100循环)
        period = 120  # 120秒一个周期
        cycle_pos = (self.t % period) / period
        
        if cycle_pos < 0.5:
            # 0-50%: 结霜上升期
            frost = cycle_pos * 2 * 100
        else:
            # 50-100%: 除霜后快速下降
            frost = max(0, 100 - (cycle_pos - 0.5) * 2 * 100)
        
        # 添加一些噪声
        if HAS_NUMPY:
            noise = np.random.normal(0, 0.5)
        else:
            noise = (hash(str(self.t)) % 100) / 50 - 1
        
        frost = max(0, min(100, frost + noise))
        
        # 温度与结霜率负相关
        temp = 18.0 - frost * 0.08 + (hash(str(self.t * 2)) % 40) / 20 - 1
        humidity = 55 + frost * 0.15 + (hash(str(self.t * 3)) % 30) / 10 - 1.5
        
        return {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'temperature': round(temp, 2),
            'humidity': round(humidity, 2),
            'voltage': round(220 + (hash(str(self.t * 4)) % 100) / 10 - 5, 2),
            'current': round(5 + frost * 0.02 + (hash(str(self.t * 5)) % 40) / 20 - 1, 2),
            'power': round(1100 + frost * 5 + (hash(str(self.t * 6)) % 200) / 10 - 10, 2),
            'frost': round(frost, 2),
            'comp': self.comp,
            'fan': self.fan,
            'door': self.door,
        }

    def _on_data(self, data):
        state.current_data = data
        state.record_count += 1
        
        # 报警逻辑
        self._check_alarms(data)
        
        # 追加历史
        state.data_history.append(data)
        if len(state.data_history) > state.max_history:
            state.data_history = state.data_history[-state.max_history:]

    def _check_alarms(self, data):
        now = time.time()
        alarms = []
        
        if data['temperature'] > 22:
            if now - state.last_alarm_time.get('temp_high', 0) > 30:
                alarms.append({'level': 'error', 'message': '温度过高 (>22°C)', 'timestamp': data['timestamp']})
                state.last_alarm_time['temp_high'] = now
        elif data['temperature'] > 20:
            if now - state.last_alarm_time.get('temp_warn', 0) > 60:
                alarms.append({'level': 'warning', 'message': '温度偏高 (>20°C)', 'timestamp': data['timestamp']})
                state.last_alarm_time['temp_warn'] = now
        
        if data['frost'] > 85:
            if now - state.last_alarm_time.get('frost_high', 0) > 30:
                alarms.append({'level': 'critical', 'message': '结霜率过高 (>85%)', 'timestamp': data['timestamp']})
                state.last_alarm_time['frost_high'] = now
        elif data['frost'] > 70:
            if now - state.last_alarm_time.get('frost_mid', 0) > 60:
                alarms.append({'level': 'warning', 'message': '结霜率较高 (>70%)', 'timestamp': data['timestamp']})
                state.last_alarm_time['frost_mid'] = now
        
        if data['door'] == 1:
            alarms.append({'level': 'info', 'message': '门已打开', 'timestamp': data['timestamp']})
        
        state.alarms = state.alarms[-49:] + alarms


# ============================================================
# AI预测（简化版，兼容有无LightGBM）
# ============================================================
def run_ai_prediction():
    """运行AI趋势分析"""
    if not state.data_history:
        return None
    
    history = state.data_history[-min(60, len(state.data_history)):]
    frost_vals = [d['frost'] for d in history]
    
    if len(frost_vals) < 5:
        return {'status': 'low_confidence', 'reason': '数据不足'}
    
    current_frost = frost_vals[-1]
    
    # 简单线性趋势分析
    if HAS_NUMPY and len(frost_vals) >= 10:
        x = np.arange(len(frost_vals))
        coef = np.polyfit(x, frost_vals, 1)[0]
        trend = 'rising' if coef > 0.3 else ('falling' if coef < -0.3 else 'stable')
        hours_to_full = (100 - current_frost) / coef if coef > 0.1 and current_frost < 100 else None
    else:
        # 无numpy时用简单差分
        recent = sum(frost_vals[-3:]) / 3
        older = sum(frost_vals[-6:-3]) / 3 if len(frost_vals) >= 6 else recent
        diff = recent - older
        trend = 'rising' if diff > 1 else ('falling' if diff < -1 else 'stable')
        hours_to_full = None
    
    # 除霜建议
    if current_frost >= 85:
        advice = '立即除霜'
        advice_color = '#dc3545'
        advice_icon = '🚨'
    elif current_frost >= 70:
        advice = '建议近期除霜'
        advice_color = '#ffc107'
        advice_icon = '⚠️'
    elif current_frost >= 50:
        advice = '关注结霜趋势'
        advice_color = '#17a2b8'
        advice_icon = '👀'
    else:
        advice = '暂不需除霜'
        advice_color = '#28a745'
        advice_icon = '✅'
    
    trend_icons = {'rising': '📈', 'falling': '📉', 'stable': '➡️'}
    trend_texts = {'rising': '结霜率上升中', 'falling': '结霜率下降中', 'stable': '结霜率稳定'}
    trend_colors = {'rising': '#ff6b6b', 'falling': '#4ecdc4', 'stable': '#aaa'}
    
    confidence = 'high' if len(frost_vals) >= 60 else ('medium' if len(frost_vals) >= 20 else 'low')
    
    return {
        'frost_pred': round(current_frost, 2),
        'frost_actual': round(current_frost, 2),
        'trend': trend,
        'trend_icon': trend_icons[trend],
        'trend_desc': trend_texts[trend],
        'trend_color': trend_colors[trend],
        'defrost_advice': advice,
        'defrost_icon': advice_icon,
        'defrost_color': advice_color,
        'change_rate': round((frost_vals[-1] - frost_vals[0]) / len(frost_vals) * 60, 3) if len(frost_vals) > 1 else 0,
        'future_trend': f"预计 {hours_to_full:.1f}h 后达100%" if hours_to_full else '暂无足够数据' if len(frost_vals) < 10 else '结霜趋势平稳',
        'confidence': confidence,
        'model_ready': True,
        'ai_active': HAS_LIGHTGBM and state.ai_loaded
    }


# ============================================================
# HTML模板（内嵌，全部零外部依赖）
# ============================================================
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>串口监控系统</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:#eee;min-height:100vh}
.header{background:rgba(0,0,0,.3);padding:15px 30px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,.1)}
.header h1{font-size:1.4rem;color:#4ecdc4}
.header-right{display:flex;gap:15px;align-items:center}
.header-right span{font-size:.85rem;opacity:.8}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.dot-green{background:#28a745;box-shadow:0 0 10px #28a745}
.dot-red{background:#dc3545;box-shadow:0 0 10px #dc3545}
.dot-yellow{background:#ffc107;box-shadow:0 0 10px #ffc107}

.layout{display:flex;min-height:calc(100vh - 60px)}
.sidebar{width:250px;background:rgba(0,0,0,.2);padding:20px;border-right:1px solid rgba(255,255,255,.1)}
.main{flex:1;padding:20px;overflow-y:auto}

.panel{background:rgba(255,255,255,.05);border-radius:10px;padding:15px;margin-bottom:15px}
.panel h3{font-size:.95rem;margin-bottom:12px;color:#4ecdc4;display:flex;align-items:center;gap:6px}

.btn{width:100%;padding:10px;border:none;border-radius:8px;font-size:.95rem;font-weight:bold;cursor:pointer;transition:all .2s;margin-bottom:8px;color:#fff}
.btn:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,.3)}
.btn:active{transform:translateY(0)}
.btn-green{background:#28a745}
.btn-red{background:#dc3545}
.btn-blue{background:#17a2b8}
.btn-gray{background:#6c757d}

.form-group{margin-bottom:10px}
.form-group label{font-size:.8rem;opacity:.7;display:block;margin-bottom:4px}
.form-group select,.form-group input{width:100%;padding:7px;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.2);border-radius:5px;color:#fff;font-size:.9rem}

.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:15px}
.metric{background:rgba(255,255,255,.05);border-radius:10px;padding:15px;text-align:center;transition:all .2s}
.metric:hover{background:rgba(255,255,255,.1);transform:translateY(-2px)}
.metric-icon{font-size:1.8rem;margin-bottom:6px}
.metric-val{font-size:1.8rem;font-weight:bold;margin:6px 0}
.metric-label{font-size:.8rem;opacity:.6}

.t{color:#ff6b6b}.h{color:#4ecdc4}.v{color:#45b7d1}.f{color:#a8e6cf}.a{color:#ffc107}.r{color:#dda0dd}

.section{background:rgba(255,255,255,.05);border-radius:10px;padding:15px;margin-bottom:15px}
.section h3{color:#4ecdc4;margin-bottom:12px;font-size:.95rem}

.alarm{border-left:3px solid;padding:8px 12px;border-radius:5px;margin-bottom:6px;display:flex;justify-content:space-between;font-size:.85rem}
.alarm-critical{background:rgba(220,53,69,.25);border-color:#dc3545}
.alarm-error{background:rgba(255,127,14,.25);border-color:#ff7f0e}
.alarm-warning{background:rgba(255,193,7,.25);border-color:#ffc107}
.alarm-info{background:rgba(23,162,184,.25);border-color:#17a2b8}

.ai-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px}
.ai-card{background:rgba(0,0,0,.2);border-radius:8px;padding:12px;text-align:center}
.ai-card-label{font-size:.75rem;opacity:.6;margin-bottom:6px}
.ai-card-val{font-size:1.6rem;font-weight:bold}
.ai-advice{background:rgba(0,0,0,.2);border-radius:8px;padding:10px;text-align:center;border:2px solid}
.ai-advice-label{font-size:.75rem;opacity:.6;margin-bottom:4px}
.ai-advice-val{font-size:1.1rem;font-weight:bold}

.chart{height:280px;background:rgba(0,0,0,.1);border-radius:8px;overflow:hidden}
.chart canvas{width:100%;height:100%}

table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid rgba(255,255,255,.06)}
th{color:#4ecdc4;font-weight:600}
tr:hover{background:rgba(255,255,255,.04)}
.ts{opacity:.6;font-size:.8rem}

.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:bold}
.bg-green{background:#28a745}.bg-red{background:#dc3545}.bg-yellow{background:#ffc107;color:#000}

.no-data{text-align:center;padding:30px;color:rgba(255,255,255,.4);font-size:.9rem}
.no-data-icon{font-size:2.5rem;margin-bottom:10px;opacity:.5}
</style>
</head>
<body>

<div class="header">
  <h1>📡 串口数据监控系统</h1>
  <div class="header-right">
    <div><span class="status-dot" id="runDot"></span> <span id="runText"></span></div>
    <div><span class="status-dot dot-yellow" id="simDot"></span> <span>模拟器</span></div>
    <div style="opacity:.6">📊 <span id="recordCount">0</span> 条</div>
  </div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="panel">
      <h3>🎭 模拟器</h3>
      <div class="form-group">
        <label>数据间隔</label>
        <select id="simInterval">
          <option value="0.5">0.5秒 (快速)</option>
          <option value="1" selected>1秒 (正常)</option>
          <option value="2">2秒 (慢速)</option>
        </select>
      </div>
      <button class="btn btn-green" id="btnSimStart" onclick="toggleSim()">▶ 启用模拟器</button>
    </div>
    <div class="panel">
      <h3>▶️ 控制</h3>
      <button class="btn btn-blue" id="btnMonitor" onclick="toggleMonitor()">▶ 开始监控</button>
      <button class="btn btn-gray" onclick="exportCSV()">📥 导出CSV</button>
      <button class="btn btn-gray" onclick="exportJSON()">📄 导出JSON</button>
      <button class="btn btn-red" onclick="clearData()">🗑️ 清空</button>
    </div>
  </div>

  <div class="main">
    <!-- 指标卡片 -->
    <div class="metrics">
      <div class="metric">
        <div class="metric-icon t">🌡️</div>
        <div class="metric-val t" id="mTemp">--°C</div>
        <div class="metric-label">温度</div>
      </div>
      <div class="metric">
        <div class="metric-icon h">💧</div>
        <div class="metric-val h" id="mHum">--%</div>
        <div class="metric-label">湿度</div>
      </div>
      <div class="metric">
        <div class="metric-icon v">⚡</div>
        <div class="metric-val v" id="mVolt">--V</div>
        <div class="metric-label">电压</div>
      </div>
      <div class="metric">
        <div class="metric-icon f">❄️</div>
        <div class="metric-val f" id="mFrost">--%</div>
        <div class="metric-label">结霜率</div>
      </div>
      <div class="metric">
        <div class="metric-icon a">⚠️</div>
        <div class="metric-val a" id="mAlarms">0</div>
        <div class="metric-label">活跃报警</div>
      </div>
      <div class="metric">
        <div class="metric-icon r">📊</div>
        <div class="metric-val r" id="mRecords">0</div>
        <div class="metric-label">记录总数</div>
      </div>
    </div>

    <!-- 报警面板 -->
    <div class="section" id="alarmSection">
      <h3>⚠️ 报警状态</h3>
      <div id="alarmList"><div class="no-data"><div class="no-data-icon">✅</div>暂无报警</div></div>
    </div>

    <!-- AI分析 -->
    <div class="section" id="aiSection">
      <h3>🧠 AI趋势分析 <span id="aiConf" style="font-size:.75rem;opacity:.5;font-weight:normal"></span></h3>
      <div class="ai-grid">
        <div class="ai-card">
          <div class="ai-card-label">预测结霜率</div>
          <div class="ai-card-val f" id="aiFrost">--%</div>
        </div>
        <div class="ai-card">
          <div class="ai-card-label">趋势判断</div>
          <div class="ai-card-val" id="aiTrend">--</div>
        </div>
        <div class="ai-card">
          <div class="ai-card-label">变化率</div>
          <div class="ai-card-val" id="aiRate">--%/h</div>
        </div>
        <div class="ai-card">
          <div class="ai-card-label">置信度</div>
          <div class="ai-card-val" id="aiConf2">--</div>
        </div>
      </div>
      <div class="ai-advice" id="aiAdvice">
        <div class="ai-advice-label">除霜建议</div>
        <div class="ai-advice-val" id="aiAdviceVal">启动监控收集数据后分析</div>
      </div>
      <div style="margin-top:8px;padding:8px;background:rgba(78,205,196,.08);border-radius:6px;font-size:.85rem;color:rgba(255,255,255,.6)" id="aiFuture">🔮 未来趋势: --</div>
    </div>

    <!-- 图表 -->
    <div class="section">
      <h3>📈 实时趋势</h3>
      <div class="chart"><canvas id="chart"></canvas></div>
    </div>

    <!-- 数据表 -->
    <div class="section">
      <h3>📋 最新数据</h3>
      <div style="max-height:300px;overflow-y:auto">
        <table>
          <thead>
            <tr><th>时间</th><th>温度</th><th>湿度</th><th>电压</th><th>电流</th><th>功率</th><th>结霜率</th><th>压缩机</th><th>风扇</th><th>门</th></tr>
          </thead>
          <tbody id="dataTable"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
// ================================================================
// 通信
// ================================================================
let pollTimer = null;
let chartData = [];

function api(url, method, body) {
  console.log('[API]', method || 'GET', url, body || '');
  return fetch(url, {
    method: method || 'GET',
    headers: body ? {'Content-Type':'application/json'} : {},
    body: body ? JSON.stringify(body) : undefined
  }).then(r => {
    console.log('[API] response status:', r.status);
    return r.json();
  }).catch(err => {
    console.error('[API] ERROR:', err);
    return {ok: false, error: err.message};
  });
}

function poll() {
  api('/api/status').then(data => {
    console.log('[POLL] data received, record_count:', data.record_count, 'frost:', data.current ? data.current.frost : 'N/A');
    try {
      updateUI(data);
    } catch(e) {
      console.error('[POLL] updateUI error:', e);
    }
  });
}

function toggleSim() {
  console.log('[SIM] toggleSim clicked');
  const interval = parseFloat(document.getElementById('simInterval').value);
  const simStart = document.getElementById('btnSimStart');
  if (simStart.textContent.includes('启用')) {
    api('/api/sim/start', 'POST', {interval: interval}).then(data => {
      console.log('[SIM] start response:', JSON.stringify(data));
      simStart.textContent = '⏹ 关闭模拟器';
      simStart.className = 'btn btn-red';
      document.getElementById('simDot').className = 'status-dot dot-green';
      // 模拟器启动后自动同步监控状态
      if (data.running) {
        state.monitorRunning = true;
        const btn = document.getElementById('btnMonitor');
        btn.textContent = '⏸ 暂停监控';
        btn.className = 'btn btn-red';
        document.getElementById('runDot').className = 'status-dot dot-green';
        document.getElementById('runText').textContent = '运行中';
      }
    });
  } else {
    console.log('[SIM] stopping simulator...');
    api('/api/sim/stop', 'POST').then(data => {
      console.log('[SIM] stop response:', JSON.stringify(data));
      simStart.textContent = '▶ 启用模拟器';
      simStart.className = 'btn btn-green';
      document.getElementById('simDot').className = 'status-dot dot-yellow';
    });
  }
}

function toggleMonitor() {
  console.log('[MON] toggleMonitor clicked, state.monitorRunning:', state.monitorRunning);
  const btn = document.getElementById('btnMonitor');
  const url = state.monitorRunning ? '/api/monitor/stop' : '/api/monitor/start';
  api(url, 'POST').then(data => {
    console.log('[MON] response:', JSON.stringify(data));
    state.monitorRunning = data.running;
    btn.textContent = data.running ? '⏸ 暂停监控' : '▶ 开始监控';
    btn.className = data.running ? 'btn btn-red' : 'btn btn-blue';
    document.getElementById('runDot').className = 'status-dot ' + (data.running ? 'dot-green' : 'dot-red');
    document.getElementById('runText').textContent = data.running ? '运行中' : '已停止';
  });
}

function updateUI(data) {
  try { _updateUI(data); } catch(e) { console.error('[UI] error:', e); }
}
function _updateUI(data) {
  // 指标
  if (data.current) {
    document.getElementById('mTemp').textContent = data.current.temperature + '°C';
    document.getElementById('mHum').textContent = data.current.humidity + '%';
    document.getElementById('mVolt').textContent = data.current.voltage + 'V';
    document.getElementById('mFrost').textContent = data.current.frost + '%';
  }
  document.getElementById('mAlarms').textContent = data.alarm_count || 0;
  document.getElementById('mRecords').textContent = data.record_count || 0;
  document.getElementById('recordCount').textContent = data.record_count || 0;

  // 报警
  const alarmList = document.getElementById('alarmList');
  if (data.alarms && data.alarms.length > 0) {
    alarmList.innerHTML = data.alarms.slice(-5).map(a =>
      `<div class="alarm alarm-${a.level}">
        <span>🔔 ${a.message}</span>
        <span class="ts">${a.timestamp ? a.timestamp.substring(11) : ''}</span>
      </div>`
    ).join('');
  } else {
    alarmList.innerHTML = '<div class="no-data"><div class="no-data-icon">✅</div>暂无报警</div>';
  }

  // AI分析
  if (data.ai) {
    document.getElementById('aiFrost').textContent = data.ai.frost_pred + '%';
    document.getElementById('aiTrend').innerHTML = `${data.ai.trend_icon} ${data.ai.trend_desc}`;
    document.getElementById('aiTrend').style.color = data.ai.trend_color;
    document.getElementById('aiRate').textContent = data.ai.change_rate + '%/h';
    const confColors = {high:'#28a745', medium:'#ffc107', low:'#dc3545'};
    const confText = {high:'🟢 高', medium:'🟡 中', low:'🔴 低'};
    document.getElementById('aiConf2').textContent = confText[data.ai.confidence] || '--';
    document.getElementById('aiConf2').style.color = confColors[data.ai.confidence] || '#fff';
    document.getElementById('aiConf').textContent = `(置信度: ${confText[data.ai.confidence] || '--'})`;
    document.getElementById('aiAdviceVal').textContent = `${data.ai.defrost_icon} ${data.ai.defrost_advice}`;
    document.getElementById('aiAdvice').style.borderColor = data.ai.defrost_color;
    document.getElementById('aiAdviceVal').style.color = data.ai.defrost_color;
    document.getElementById('aiFuture').textContent = '🔮 未来趋势: ' + (data.ai.future_trend || '--');
  } else {
    document.getElementById('aiFrost').textContent = '--%';
    document.getElementById('aiTrend').textContent = '--';
  }

  // 数据表
  if (data.history && data.history.length > 0) {
    document.getElementById('dataTable').innerHTML = data.history.slice(-20).reverse().map(d => `
      <tr>
        <td class="ts">${d.timestamp ? d.timestamp.substring(11) : '--'}</td>
        <td>${d.temperature}</td>
        <td>${d.humidity}</td>
        <td>${d.voltage}</td>
        <td>${d.current}</td>
        <td>${d.power}</td>
        <td style="color:${d.frost>70?'#ff6b6b':'#a8e6cf'}">${d.frost}</td>
        <td>${d.comp?'🟢':'🔴'}</td>
        <td>${d.fan?'🟢':'🔴'}</td>
        <td>${d.door?'🟡':'🟢'}</td>
      </tr>
    `).join('');

    // 图表数据
    chartData = data.history.slice(-60);
    drawChart();
  }
}

// ================================================================
// 简易图表（Canvas，无任何库依赖）
// ================================================================
function drawChart() {
  const canvas = document.getElementById('chart');
  const ctx = canvas.getContext('2d');
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width;
  canvas.height = rect.height;

  if (chartData.length < 2) return;

  const w = canvas.width, h = canvas.height;
  const pad = {top: 20, right: 15, bottom: 30, left: 45};
  const cw = w - pad.left - pad.right;
  const ch = h - pad.top - pad.bottom;

  ctx.clearRect(0, 0, w, h);

  // 背景
  ctx.fillStyle = 'rgba(0,0,0,0.15)';
  ctx.fillRect(0, 0, w, h);

  // 网格
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const y = pad.top + (ch / 5) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + cw, y);
    ctx.stroke();
    // 标签
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.font = '10px Segoe UI';
    ctx.textAlign = 'right';
    const val = (100 - (i / 5) * 100).toFixed(0);
    ctx.fillText(val, pad.left - 5, y + 3);
  }

  // Y轴标题
  ctx.save();
  ctx.fillStyle = 'rgba(255,255,255,0.4)';
  ctx.font = '10px Segoe UI';
  ctx.textAlign = 'center';
  ctx.translate(12, h / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('结霜率 / 温度', 0, 0);
  ctx.restore();

  // X轴标签
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.font = '10px Segoe UI';
  ctx.textAlign = 'center';
  const step = Math.max(1, Math.floor(chartData.length / 6));
  for (let i = 0; i < chartData.length; i += step) {
    const x = pad.left + (i / (chartData.length - 1)) * cw;
    const label = chartData[i].timestamp ? chartData[i].timestamp.substring(11, 16) : '';
    ctx.fillText(label, x, h - 8);
  }

  // 数据线函数
  function drawLine(key, color, label) {
    if (!chartData || chartData.length < 2) return;
    const vals = chartData.map(d => d[key]);
    const minV = Math.min(...vals);
    const maxV = Math.max(...vals);
    const range = maxV - minV || 1;

    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    for (let i = 0; i < chartData.length; i++) {
      const x = pad.left + (i / (chartData.length - 1)) * cw;
      const y = pad.top + (1 - (vals[i] - minV) / range) * ch;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // 图例
    ctx.fillStyle = color;
    ctx.fillRect(pad.left + cw - 100 + ['结霜率','温度'].indexOf(label) * 50, pad.top - 15, 10, 10);
    ctx.fillStyle = 'rgba(255,255,255,0.6)';
    ctx.font = '11px Segoe UI';
    ctx.textAlign = 'left';
    ctx.fillText(label, pad.left + cw - 85 + ['结霜率','温度'].indexOf(label) * 50, pad.top - 5);
  }

  drawLine('frost', '#a8e6cf', '结霜率');
  drawLine('temperature', '#ff6b6b', '温度');
}

// 窗口大小变化时重绘
window.addEventListener('resize', () => drawChart());

// ================================================================
// 数据导出
// ================================================================
function exportCSV() {
  if (!chartData.length) return alert('无数据可导出');
  const header = '时间,温度,湿度,电压,电流,功率,结霜率,压缩机,风扇,门\\n';
  const rows = chartData.map(d =>
    `${d.timestamp},${d.temperature},${d.humidity},${d.voltage},${d.current},${d.power},${d.frost},${d.comp},${d.fan},${d.door}`
  ).join('\\n');
  download(`${getDateStr()}_serial_data.csv`, header + rows, 'text/csv');
}

function exportJSON() {
  if (!chartData.length) return alert('无数据可导出');
  download(`${getDateStr()}_serial_data.json`, JSON.stringify(chartData, null, 2), 'application/json');
}

function clearData() {
  if (!confirm('确定清空所有数据?')) return;
  api('/api/clear', 'POST').then(() => {
    chartData = [];
    drawChart();
    document.getElementById('dataTable').innerHTML = '';
    document.getElementById('alarmList').innerHTML = '<div class="no-data"><div class="no-data-icon">✅</div>暂无报警</div>';
    ['mTemp','mHum','mVolt','mFrost'].forEach(id => document.getElementById(id).textContent = '--');
    ['mAlarms','mRecords'].forEach(id => document.getElementById(id).textContent = '0');
    ['aiFrost','aiTrend','aiRate','aiConf2'].forEach(id => document.getElementById(id).textContent = '--');
    document.getElementById('aiAdviceVal').textContent = '启动监控收集数据后分析';
  });
}

function download(filename, content, type) {
  const blob = new Blob([content], {type});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

function getDateStr() {
  return new Date().toISOString().replace(/T/g,'_').substring(0,19).replace(/:/g,'-');
}

// ================================================================
// 启动
// ================================================================
let state = {monitorRunning: false};
poll();
setInterval(poll, 2000);
</script>
</body>
</html>
"""


# ============================================================
# HTTP 服务器
# ============================================================
class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 静默日志

    def _route(self, method):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            self.send_html(HTML_PAGE)
        elif path == '/api/status':
            self.send_json(self._get_status())
        elif path == '/api/monitor/start' and method == 'POST':
            state.running = True
            state.start_time = time.time()
            self.send_json({'running': True})
        elif path == '/api/monitor/stop' and method == 'POST':
            state.running = False
            self.send_json({'running': False})
        elif path == '/api/sim/start' and method == 'POST':
            body = self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}'
            data = json.loads(body)
            if state.simulator:
                state.simulator.stop()
            state.running = True  # 自动开启监控
            state.start_time = time.time()
            state.simulator = ColdStorageSimulator(interval=data.get('interval', 1.0))
            state.simulator.start()
            self.send_json({'ok': True, 'running': True})
        elif path == '/api/sim/stop' and method == 'POST':
            if state.simulator:
                state.simulator.stop()
                state.simulator = None
            self.send_json({'ok': True})
        elif path == '/api/clear' and method == 'POST':
            state.data_history = []
            state.alarms = []
            state.current_data = {}
            state.record_count = 0
            state.last_alarm_time = {}
            self.send_json({'ok': True})
        elif path == '/api/export/csv':
            self._export_csv()
        elif path == '/api/export/json':
            self._export_json()
        else:
            self.send_json({'error': 'not found'}, code=404)

    def do_GET(self):
        self._route('GET')

    def do_POST(self):
        self._route('POST')

    def send_html(self, content):
        content = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, data, code=200):
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def _get_status(self):
        ai = run_ai_prediction()
        return {
            'running': state.running,
            'simulator': state.simulator is not None,
            'record_count': state.record_count,
            'alarm_count': len(state.alarms),
            'alarms': state.alarms[-5:],
            'current': state.current_data,
            'history': state.data_history[-60:],
            'ai': ai
        }

    def _export_csv(self):
        if not state.data_history:
            self.send_json({'error': 'no data'})
            return
        import io
        buf = io.StringIO()
        buf.write('时间,温度,湿度,电压,电流,功率,结霜率,压缩机,风扇,门\n')
        for d in state.data_history:
            buf.write(f"{d['timestamp']},{d['temperature']},{d['humidity']},{d['voltage']},{d['current']},{d['power']},{d['frost']},{d['comp']},{d['fan']},{d['door']}\n")
        content = buf.getvalue().encode('utf-8-sig')
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv')
        self.send_header('Content-Disposition', 'attachment; filename=data.csv')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def _export_json(self):
        if not state.data_history:
            self.send_json({'error': 'no data'})
            return
        content = json.dumps(state.data_history, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Disposition', 'attachment; filename=data.json')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)


# ============================================================
# 入口
# ============================================================
def main():
    import traceback
    _print = print
    try:
        sys.stdout.flush()
    except AttributeError:
        _print = lambda *a, **k: None

    _print("[DEBUG] main() called")

    port = 5000
    for try_port in range(5000, 5010):
        try:
            server = HTTPServer(('127.0.0.1', try_port), Handler)
            port = try_port
            break
        except OSError:
            _print(f"Port {try_port} busy, trying next...")
            continue
    else:
        _print("No available port!")
        return

    url = f'http://127.0.0.1:{port}'
    _print(f"[DEBUG] Server listening on {url}")

    # 不自动开浏览器，避免阻塞
    # try:
    #     webbrowser.open(url)
    # except Exception:
    #     pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        _print(f"[ERROR] serve_forever crashed: {e}")
        traceback.print_exc()
    finally:
        if state.simulator:
            state.simulator.stop()
        server.shutdown()


if __name__ == '__main__':
    main()
