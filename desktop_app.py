# -*- coding: utf-8 -*-
"""
串口监控系统 - pywebview 桌面版
用 pywebview JS API 桥接，Python 暴露后端函数给前端直接调用，不依赖 HTTP 服务器
图标: icons/app_icon.ico / icons/app_icon.png
无控制台窗口: 用 pythonw.exe 启动，或改名为 .pyw 双击运行
"""
import os
from pathlib import Path
import os
import sys
import json
import threading
import time
import webview  # 必须在这里 import，Api 类的 @webview.expose 装饰器依赖它
from datetime import datetime

# 可选依赖
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

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
        self.current_data = {}
        self.last_alarm_time = {}
        self.record_count = 0
        self.start_time = None

state = MonitorState()


# ============================================================
# 模拟器
# ============================================================
class ColdStorageSimulator:
    def __init__(self, interval=1.0):
        self.interval = interval
        self.running = False
        self.thread = None
        self.t = 0
        self.comp = 1
        self.fan = 1
        self.door = 0

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
        period = 120
        cycle_pos = (self.t % period) / period

        if cycle_pos < 0.5:
            frost = cycle_pos * 2 * 100
        else:
            frost = max(0, 100 - (cycle_pos - 0.5) * 2 * 100)

        if HAS_NUMPY:
            noise = np.random.normal(0, 0.5)
        else:
            noise = (hash(str(self.t)) % 100) / 50 - 1

        frost = max(0, min(100, frost + noise))
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
        self._check_alarms(data)
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
# AI分析
# ============================================================
def run_ai_prediction():
    if not state.data_history:
        return None

    history = state.data_history[-min(60, len(state.data_history)):]
    frost_vals = [d['frost'] for d in history]

    if len(frost_vals) < 5:
        return {'status': 'low_confidence', 'reason': '数据不足'}

    current_frost = frost_vals[-1]

    if HAS_NUMPY and len(frost_vals) >= 10:
        x = np.arange(len(frost_vals))
        coef = np.polyfit(x, frost_vals, 1)[0]
        trend = 'rising' if coef > 0.3 else ('falling' if coef < -0.3 else 'stable')
        hours_to_full = (100 - current_frost) / coef if coef > 0.1 and current_frost < 100 else None
    else:
        recent = sum(frost_vals[-3:]) / 3
        older = sum(frost_vals[-6:-3]) / 3 if len(frost_vals) >= 6 else recent
        diff = recent - older
        trend = 'rising' if diff > 1 else ('falling' if diff < -1 else 'stable')
        hours_to_full = None

    if current_frost >= 85:
        advice = '立即除霜'; advice_color = '#dc3545'; advice_icon = '🚨'
    elif current_frost >= 70:
        advice = '建议近期除霜'; advice_color = '#ffc107'; advice_icon = '⚠️'
    elif current_frost >= 50:
        advice = '关注结霜趋势'; advice_color = '#17a2b8'; advice_icon = '👀'
    else:
        advice = '暂不需除霜'; advice_color = '#28a745'; advice_icon = '✅'

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
        'future_trend': f"预计 {hours_to_full:.1f}h 后达100%" if hours_to_full else ('暂无足够数据' if len(frost_vals) < 10 else '结霜趋势平稳'),
        'confidence': confidence,
        'model_ready': True,
        'ai_active': HAS_LIGHTGBM
    }


# ============================================================
# 前端 API（暴露给 JavaScript，pywebview 6.x 所有 public 方法自动暴露）
# ============================================================
class Api:
    def get_status(self):
        """前端轮询状态"""
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

    def sim_start(self, interval=1.0):
        """启动模拟器"""
        if state.simulator:
            state.simulator.stop()
        state.running = True
        state.start_time = time.time()
        state.simulator = ColdStorageSimulator(interval=float(interval))
        state.simulator.start()
        return {'ok': True, 'running': True}

    def sim_stop(self):
        """停止模拟器"""
        if state.simulator:
            state.simulator.stop()
            state.simulator = None
        return {'ok': True}

    def monitor_start(self):
        """开始监控"""
        state.running = True
        state.start_time = time.time()
        return {'running': True}

    def monitor_stop(self):
        """停止监控"""
        state.running = False
        return {'running': False}

    def clear(self):
        """清空数据"""
        state.data_history = []
        state.alarms = []
        state.current_data = {}
        state.record_count = 0
        state.last_alarm_time = {}
        return {'ok': True}

    # ─── 窗口控制（frameless 用）────────────────────────
    def win_minimize(self):
        """最小化窗口"""
        try:
            import ctypes, ctypes.wintypes as wintypes
            HWND = ctypes.windll.user32.GetForegroundWindow()
            ctypes.windll.user32.ShowWindow(HWND, 6)  # SW_MINIMIZE=6
        except Exception:
            pass

    def win_maximize(self):
        """最大化窗口"""
        try:
            import ctypes
            HWND = ctypes.windll.user32.GetForegroundWindow()
            ctypes.windll.user32.ShowWindow(HWND, 3)  # SW_MAXIMIZE=3
        except Exception:
            pass

    def win_restore(self):
        """还原窗口"""
        try:
            import ctypes
            HWND = ctypes.windll.user32.GetForegroundWindow()
            ctypes.windll.user32.ShowWindow(HWND, 9)  # SW_RESTORE=9
        except Exception:
            pass

    def win_close(self):
        """关闭窗口"""
        try:
            import ctypes
            HWND = ctypes.windll.user32.GetForegroundWindow()
            ctypes.windll.user32.PostMessageW(HWND, 0x0112, 0xF060, 0)  # WM_SYSCOMMAND, SC_CLOSE
        except Exception:
            pass

    def win_is_maximized(self):
        """查询是否最大化"""
        try:
            import ctypes
            HWND = ctypes.windll.user32.GetForegroundWindow()
            return ctypes.windll.user32.IsZoomed(HWND) != 0
        except Exception:
            return False

    def export_csv(self):
        """导出CSV，返回 Base64"""
        if not state.data_history:
            return None
        import io, base64
        buf = io.StringIO()
        buf.write('时间,温度,湿度,电压,电流,功率,结霜率,压缩机,风扇,门\n')
        for d in state.data_history:
            buf.write(f"{d['timestamp']},{d['temperature']},{d['humidity']},{d['voltage']},{d['current']},{d['power']},{d['frost']},{d['comp']},{d['fan']},{d['door']}\n")
        return base64.b64encode(buf.getvalue().encode('utf-8-sig')).decode()

    def export_json(self):
        """导出JSON，返回 Base64"""
        if not state.data_history:
            return None
        import base64
        return base64.b64encode(json.dumps(state.data_history, ensure_ascii=False).encode('utf-8')).decode()


# ============================================================
# HTML 页面（内联，无外部依赖）
# ============================================================
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>串口监控系统</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:linear-gradient(135deg,#1a1a2e,#16213e);color:#eee;min-height:100vh}
/* .header removed – using custom titleBar instead */
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
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
.btn-green{background:#28a745}.btn-red{background:#dc3545}.btn-blue{background:#17a2b8}.btn-gray{background:#6c757d}

.form-group{margin-bottom:10px}
.form-group label{font-size:.8rem;opacity:.7;display:block;margin-bottom:4px}
.form-group select{width:100%;padding:7px;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.2);border-radius:5px;color:#fff;font-size:.9rem}

.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:15px}
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
.ai-advice-val{font-size:1.1rem;font-weight:bold}

.chart{height:280px;background:rgba(0,0,0,.1);border-radius:8px;overflow:hidden}
.chart canvas{width:100%;height:100%}

table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid rgba(255,255,255,.06)}
th{color:#4ecdc4;font-weight:600}
tr:hover{background:rgba(255,255,255,.04)}
.ts{opacity:.6;font-size:.8rem}

.no-data{text-align:center;padding:30px;color:rgba(255,255,255,.4);font-size:.9rem}
.no-data-icon{font-size:2.5rem;margin-bottom:10px;opacity:.5}

/* ─── 自定义标题栏 ─────────────────────────────── */
#titleBar{
  position:fixed;top:0;left:0;right:0;height:48px;z-index:9999;
  display:flex;align-items:center;justify-content:space-between;
  background:#16213e;
  border-bottom:1px solid rgba(78,205,196,.2);
  -webkit-app-region:drag;
  user-select:none;
}
#titleBar *{-webkit-app-region:no-drag}
.tb-left{display:flex;align-items:center;gap:10px;padding-left:14px;flex-shrink:0}
.tb-icon{width:22px;height:22px;border-radius:4px;flex-shrink:0}
.tb-title{font-size:.95rem;font-weight:700;color:#4ecdc4;letter-spacing:.5px}
.tb-center{display:flex;align-items:center;gap:10px;justify-content:center;overflow:hidden}
.tb-status{font-size:.8rem;color:rgba(255,255,255,.75)}
.tb-sep{color:rgba(255,255,255,.25)}
.tb-right{display:flex;align-items:center;height:100%}
.win-btn{
  width:46px;height:48px;display:flex;align-items:center;justify-content:center;
  font-size:12px;color:rgba(255,255,255,.7);cursor:pointer;transition:background .15s;
  flex-shrink:0;
}
.win-btn:hover{background:rgba(255,255,255,.1);color:#fff}
.win-close:hover{background:#e81123!important;color:#fff!important}
</style>
</head>
<body>

<!-- 自定义标题栏 -->
<div id="titleBar">
  <div class="tb-left">
    <img class="tb-icon" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAA7AAAAOwBeShxvQAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAJtSURBVFiF7Zc9aBRBFMd/s3d3jxJQUFAQBGy0FAsBC7EQK7EQsRMLsRMLsRMLsRMLsRALsRALsRALsRALsRALsRALsRALsRALsRCx0D8QWfOyuJvd8e5ldm/3eO/OlqD8YHdm3rz3m9n3+2aWAf4rJOlrA9yS1AO0Ah1AN9ANdAM9QI6c2e3u0u3u8u7dO27evM6lS5c4f/48J06c4NixYxw9epQjR45w+PBhDh06xKFDhzh48CAHDhxg37597N+/n3379rFnzx727t3Lnj172LNnD7t372bPnj3s3r2b3bt3s2vXLnbt2sWuXbvYvXs3u3fvZteuXezatYvdu3eze/dudu3axa5du9i1axdvv93D0NAQ3d3d9Pb20tPTQ29vL0NDQwwNDT3zDfwvJJVA9gO3gYPA0XqAg6TbwE3gBHCsHmCwJOnrfwB4BTgAHAYOJQP7gB7gCHA0GVgP3AcexE3yM3ALOJoM7EoG9gM9wOHkYJJ0GLgFHEkGJkuSvq8H2A8cTJL2Az3AkeRgknQQuAUcTg4mSYeAW8CR5GCSdBi4DRxJDiZJR4DbwOHkYJJ0DLgLHE0OJknHgXvA0eRgknQCuA8cSw4mSaeA+8Cx5GCSc5Kkr+sBjgBHkoNJ0nHgPnA8OZgknQHuA8eTg0nSWeA+cCI5mCSdBe4DJ5KDSdI54D5wMjmYJJ0H7gMnkoNJ0gXgPnAqOZgknQfuA6eTg0nSBeA+cDo5mCRdBO4DZ5KDSdJl4D5wLjmYJF0B7gPnk4NJ0lXgPnA+OZgkXQMuAPeSg0nSdeACcC85mCTdAC4CD5KDSdJN4CLwMDmYJN0CLgEPk4P9DfwBY9tYI5Q3jC4AAAAASUVORK5CYII=" alt="">
    <span class="tb-title">串口数据监控系统 🔴TEST🔴</span>
  </div>
  <div class="tb-center">
    <span class="dot" id="runDot"></span>
    <span id="runText" class="tb-status">已停止</span>
    <span class="dot dot-yellow" id="simDot"></span>
    <span class="tb-status">模拟器</span>
    <span class="tb-status">📊 <span id="recordCount">0</span> 条</span>
    <span style="margin-left:auto"></span>
    <b style="color:red;cursor:pointer;padding:4px 10px;background:rgba(220,53,69,.8);border-radius:4px" onclick="winClose()">✕ 关闭</b>
  </div>
</div>

<!-- 占位，防止内容被标题栏遮挡 -->
<div style="height:48px"></div>

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
    <div class="metrics">
      <div class="metric"><div class="metric-icon t">🌡️</div><div class="metric-val t" id="mTemp">--°C</div><div class="metric-label">温度</div></div>
      <div class="metric"><div class="metric-icon h">💧</div><div class="metric-val h" id="mHum">--%</div><div class="metric-label">湿度</div></div>
      <div class="metric"><div class="metric-icon v">⚡</div><div class="metric-val v" id="mVolt">--V</div><div class="metric-label">电压</div></div>
      <div class="metric"><div class="metric-icon f">❄️</div><div class="metric-val f" id="mFrost">--%</div><div class="metric-label">结霜率</div></div>
      <div class="metric"><div class="metric-icon a">⚠️</div><div class="metric-val a" id="mAlarms">0</div><div class="metric-label">活跃报警</div></div>
      <div class="metric"><div class="metric-icon r">📊</div><div class="metric-val r" id="mRecords">0</div><div class="metric-label">记录总数</div></div>
    </div>

    <div class="section">
      <h3>⚠️ 报警状态</h3>
      <div id="alarmList"><div class="no-data"><div class="no-data-icon">✅</div>暂无报警</div></div>
    </div>

    <div class="section">
      <h3>🧠 AI趋势分析 <span id="aiConfTag" style="font-size:.75rem;opacity:.5;font-weight:normal"></span></h3>
      <div class="ai-grid">
        <div class="ai-card"><div class="ai-card-label">预测结霜率</div><div class="ai-card-val f" id="aiFrost">--%</div></div>
        <div class="ai-card"><div class="ai-card-label">趋势判断</div><div class="ai-card-val" id="aiTrend">--</div></div>
        <div class="ai-card"><div class="ai-card-label">变化率</div><div class="ai-card-val" id="aiRate">--%/h</div></div>
        <div class="ai-card"><div class="ai-card-label">置信度</div><div class="ai-card-val" id="aiConf">--</div></div>
      </div>
      <div class="ai-advice" id="aiAdvice">
        <div style="font-size:.75rem;opacity:.6;margin-bottom:4px">除霜建议</div>
        <div class="ai-advice-val" id="aiAdviceVal">启动监控收集数据后分析</div>
      </div>
      <div style="margin-top:8px;padding:8px;background:rgba(78,205,196,.08);border-radius:6px;font-size:.85rem;color:rgba(255,255,255,.6)" id="aiFuture">🔮 未来趋势: --</div>
    </div>

    <div class="section">
      <h3>📈 实时趋势</h3>
      <div class="chart"><canvas id="chart"></canvas></div>
    </div>

    <div class="section">
      <h3>📋 最新数据</h3>
      <div style="max-height:300px;overflow-y:auto">
        <table>
          <thead><tr><th>时间</th><th>温度</th><th>湿度</th><th>电压</th><th>电流</th><th>功率</th><th>结霜率</th><th>压缩机</th><th>风扇</th><th>门</th></tr></thead>
          <tbody id="dataTable"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
let chartData = [];
let monitorRunning = false;
let simRunning = false;

// 通过 pywebview API 调用 Python 后端
async function getStatus() {
  try {
    return await window.pywebview.api.get_status();
  } catch(e) {
    console.error('get_status error:', e);
    return null;
  }
}

async function toggleSim() {
  const btn = document.getElementById('btnSimStart');
  const interval = parseFloat(document.getElementById('simInterval').value);
  if (!simRunning) {
    const r = await window.pywebview.api.sim_start(interval);
    if (r && r.running) {
      simRunning = true; monitorRunning = true;
      btn.textContent = '⏹ 关闭模拟器'; btn.className = 'btn btn-red';
      document.getElementById('simDot').className = 'dot dot-green';
      document.getElementById('btnMonitor').textContent = '⏸ 暂停监控';
      document.getElementById('btnMonitor').className = 'btn btn-red';
      document.getElementById('runDot').className = 'dot dot-green';
      document.getElementById('runText').textContent = '运行中';
    }
  } else {
    await window.pywebview.api.sim_stop();
    simRunning = false; monitorRunning = false;
    btn.textContent = '▶ 启用模拟器'; btn.className = 'btn btn-green';
    document.getElementById('simDot').className = 'dot dot-yellow';
    document.getElementById('runDot').className = 'dot dot-red';
    document.getElementById('runText').textContent = '已停止';
  }
}

async function toggleMonitor() {
  const url = monitorRunning ? 'monitor_stop' : 'monitor_start';
  const r = monitorRunning
    ? await window.pywebview.api.monitor_stop()
    : await window.pywebview.api.monitor_start();
  monitorRunning = r.running;
  const btn = document.getElementById('btnMonitor');
  btn.textContent = monitorRunning ? '⏸ 暂停监控' : '▶ 开始监控';
  btn.className = monitorRunning ? 'btn btn-red' : 'btn btn-blue';
  document.getElementById('runDot').className = 'dot ' + (monitorRunning ? 'dot-green' : 'dot-red');
  document.getElementById('runText').textContent = monitorRunning ? '运行中' : '已停止';
}

async function clearData() {
  if (!confirm('确定清空所有数据?')) return;
  await window.pywebview.api.clear();
  chartData = [];
  drawChart();
  ['mTemp','mHum','mVolt','mFrost'].forEach(id => document.getElementById(id).textContent = '--');
  ['mAlarms','mRecords'].forEach(id => document.getElementById(id).textContent = '0');
  document.getElementById('alarmList').innerHTML = '<div class="no-data"><div class="no-data-icon">✅</div>暂无报警</div>';
  document.getElementById('aiAdviceVal').textContent = '启动监控收集数据后分析';
  document.getElementById('dataTable').innerHTML = '';
}

function updateUI(data) {
  if (!data) return;
  if (data.current) {
    document.getElementById('mTemp').textContent = data.current.temperature + '°C';
    document.getElementById('mHum').textContent = data.current.humidity + '%';
    document.getElementById('mVolt').textContent = data.current.voltage + 'V';
    document.getElementById('mFrost').textContent = data.current.frost + '%';
  }
  document.getElementById('mAlarms').textContent = data.alarm_count || 0;
  document.getElementById('mRecords').textContent = data.record_count || 0;
  document.getElementById('recordCount').textContent = data.record_count || 0;

  if (data.alarms && data.alarms.length > 0) {
    document.getElementById('alarmList').innerHTML = data.alarms.slice(-5).map(a =>
      '<div class="alarm alarm-' + a.level + '"><span>🔔 ' + a.message + '</span><span class="ts">' +
      (a.timestamp ? a.timestamp.substring(11) : '') + '</span></div>'
    ).join('');
  } else {
    document.getElementById('alarmList').innerHTML = '<div class="no-data"><div class="no-data-icon">✅</div>暂无报警</div>';
  }

  if (data.ai) {
    document.getElementById('aiFrost').textContent = data.ai.frost_pred + '%';
    document.getElementById('aiTrend').innerHTML = data.ai.trend_icon + ' ' + data.ai.trend_desc;
    document.getElementById('aiTrend').style.color = data.ai.trend_color;
    document.getElementById('aiRate').textContent = data.ai.change_rate + '%/h';
    const confColors = {high:'#28a745', medium:'#ffc107', low:'#dc3545'};
    const confText = {high:'🟢 高', medium:'🟡 中', low:'🔴 低'};
    document.getElementById('aiConf').textContent = confText[data.ai.confidence] || '--';
    document.getElementById('aiConf').style.color = confColors[data.ai.confidence] || '#fff';
    document.getElementById('aiConfTag').textContent = '(置信度: ' + (confText[data.ai.confidence] || '--') + ')';
    document.getElementById('aiAdviceVal').innerHTML = data.ai.defrost_icon + ' ' + data.ai.defrost_advice;
    document.getElementById('aiAdvice').style.borderColor = data.ai.defrost_color;
    document.getElementById('aiAdviceVal').style.color = data.ai.defrost_color;
    document.getElementById('aiFuture').textContent = '🔮 未来趋势: ' + (data.ai.future_trend || '--');
  }

  if (data.history && data.history.length > 0) {
    chartData = data.history.slice(-60);
    document.getElementById('dataTable').innerHTML = data.history.slice(-20).reverse().map(d =>
      '<tr><td class="ts">' + (d.timestamp ? d.timestamp.substring(11) : '--') + '</td>' +
      '<td>' + d.temperature + '</td><td>' + d.humidity + '</td><td>' + d.voltage + '</td>' +
      '<td>' + d.current + '</td><td>' + d.power + '</td>' +
      '<td style="color:' + (d.frost>70?'#ff6b6b':'#a8e6cf') + '">' + d.frost + '</td>' +
      '<td>' + (d.comp?'🟢':'🔴') + '</td><td>' + (d.fan?'🟢':'🔴') + '</td><td>' + (d.door?'🟡':'🟢') + '</td></tr>'
    ).join('');
    drawChart();
  }
}

function drawChart() {
  const canvas = document.getElementById('chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const parent = canvas.parentElement;
  canvas.width = parent.clientWidth;
  canvas.height = parent.clientHeight;
  if (chartData.length < 2) return;

  const w = canvas.width, h = canvas.height;
  const pad = {top:20, right:15, bottom:30, left:45};
  const cw = w - pad.left - pad.right;
  const ch = h - pad.top - pad.bottom;

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = 'rgba(0,0,0,0.15)';
  ctx.fillRect(0, 0, w, h);

  ctx.strokeStyle = 'rgba(255,255,255,0.06)'; ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const y = pad.top + (ch / 5) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + cw, y); ctx.stroke();
    ctx.fillStyle = 'rgba(255,255,255,0.3)'; ctx.font = '10px Segoe UI'; ctx.textAlign = 'right';
    ctx.fillText((100 - (i / 5) * 100).toFixed(0), pad.left - 5, y + 3);
  }

  ctx.fillStyle = 'rgba(255,255,255,0.3)'; ctx.font = '10px Segoe UI'; ctx.textAlign = 'center';
  const step = Math.max(1, Math.floor(chartData.length / 6));
  for (let i = 0; i < chartData.length; i += step) {
    const x = pad.left + (i / (chartData.length - 1)) * cw;
    ctx.fillText(chartData[i].timestamp ? chartData[i].timestamp.substring(11, 16) : '', x, h - 8);
  }

  const frostVals = chartData.map(d => d.frost);
  const fMin = Math.min(...frostVals), fMax = Math.max(...frostVals);
  const fRange = fMax - fMin || 1;
  ctx.beginPath(); ctx.strokeStyle = '#a8e6cf'; ctx.lineWidth = 2;
  for (let i = 0; i < chartData.length; i++) {
    const x = pad.left + (i / (chartData.length - 1)) * cw;
    const y = pad.top + (1 - (frostVals[i] - fMin) / fRange) * ch;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();

  const tempVals = chartData.map(d => d.temperature);
  const tMin = Math.min(...tempVals), tMax = Math.max(...tempVals);
  const tRange = tMax - tMin || 1;
  ctx.beginPath(); ctx.strokeStyle = '#ff6b6b'; ctx.lineWidth = 2;
  for (let i = 0; i < chartData.length; i++) {
    const x = pad.left + (i / (chartData.length - 1)) * cw;
    const y = pad.top + (1 - (tempVals[i] - tMin) / tRange) * ch;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.fillStyle = '#a8e6cf'; ctx.fillRect(pad.left + cw - 110, pad.top - 15, 10, 10);
  ctx.fillStyle = 'rgba(255,255,255,0.6)'; ctx.font = '11px Segoe UI'; ctx.textAlign = 'left';
  ctx.fillText('结霜率', pad.left + cw - 95, pad.top - 5);
  ctx.fillStyle = '#ff6b6b'; ctx.fillRect(pad.left + cw - 55, pad.top - 15, 10, 10);
  ctx.fillText('温度', pad.left + cw - 40, pad.top - 5);
}

window.addEventListener('resize', () => drawChart());

// 导出用 pywebview JS API 取 Base64 数据后下载
async function exportCSV() {
  const b64 = await window.pywebview.api.export_csv();
  if (!b64) { alert('无数据可导出'); return; }
  download('data.csv', atob(b64), 'text/csv;charset=utf-8-sig');
}

async function exportJSON() {
  const b64 = await window.pywebview.api.export_json();
  if (!b64) { alert('无数据可导出'); return; }
  download('data.json', atob(b64), 'application/json');
}

function download(filename, content, type) {
  const blob = new Blob([content], {type});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// 轮询
async function poll() {
  const data = await getStatus();
  if (data) updateUI(data);
}

document.getElementById('runDot').className = 'dot dot-red';
document.getElementById('runText').textContent = '已停止';

poll();
setInterval(poll, 2000);

// ─── 自定义标题栏窗口控制 ─────────────────────────────
let isMaximized = false;

async function winMinimize() { await pywebview.api.win_minimize(); }
async function winMaximize() {
    isMaximized = !isMaximized;
    if (isMaximized) await pywebview.api.win_maximize();
    else await pywebview.api.win_restore();
}
async function winClose() { await pywebview.api.win_close(); }

// 双击标题栏：最大化/还原
document.addEventListener('DOMContentLoaded', () => {
    const tb = document.getElementById('titleBar');
    if (tb) {
        tb.addEventListener('dblclick', (e) => {
            if (!e.target.closest('.win-btn')) winMaximize();
        });
    }
    // 启动时同步最大化状态
    pywebview.api.win_is_maximized().then(v => {
        isMaximized = v;
        const icon = document.getElementById('winMaxIcon');
        if (icon) icon.textContent = isMaximized ? '❐' : '□';
    });
});
</script>
</body>
</html>
"""


# ============================================================
# 入口
# ============================================================
def main():
    api = Api()

    window = webview.create_window(
        title='串口数据监控系统 v1.0',
        html=HTML_PAGE,
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
        js_api=api,
        frameless=True,
    )

    webview.start(debug=False)


if __name__ == '__main__':
    main()
