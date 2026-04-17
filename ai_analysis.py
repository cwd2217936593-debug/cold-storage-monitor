"""
AI趋势分析模块 - 集成LightGBM结霜率预测模型
"""
import numpy as np
import pandas as pd
import os
from datetime import datetime
import joblib

# 模型路径
MODEL_PATH = r'C:\Users\22179\.qclaw\workspace-agent-a69f0ee3\frost_control\frost_model.pkl'

# 全局状态
_model = None
_feature_cols = None
_params = None
_history_buffer = []  # 历史数据缓冲区（用于计算滞后特征）
MAX_BUFFER = 120  # 最多保留120分钟历史


def load_model():
    """加载训练好的LightGBM模型"""
    global _model, _feature_cols, _params
    
    if _model is not None:
        return True
    
    if not os.path.exists(MODEL_PATH):
        print(f"[AI] 模型文件不存在: {MODEL_PATH}")
        return False
    
    try:
        data = joblib.load(MODEL_PATH)
        _model = data['model']
        _feature_cols = data['feature_cols']
        _params = data['params']
        print(f"[AI] 模型加载成功，特征数: {len(_feature_cols)}")
        return True
    except Exception as e:
        print(f"[AI] 模型加载失败: {e}")
        return False


def compute_features(df_window):
    """
    从历史窗口数据计算模型所需的28个特征
    df_window: 包含历史数据的DataFrame，至少需要有当前行
    """
    if len(df_window) < 1:
        return None
    
    # 取最后一行作为当前数据
    row = df_window.iloc[-1].copy()
    
    # === 时间特征 ===
    ts = pd.to_datetime(row['timestamp']) if 'timestamp' in row else datetime.now()
    hour = ts.hour
    minute = ts.minute
    dayofweek = ts.dayofweek
    day = ts.day
    
    # === 周期性特征 ===
    hour_sin = np.sin(2 * np.pi * hour / 24)
    hour_cos = np.cos(2 * np.pi * hour / 24)
    day_sin = np.sin(2 * np.pi * dayofweek / 7)
    day_cos = np.cos(2 * np.pi * dayofweek / 7)
    
    # === 滞后特征（从历史数据计算）===
    frost_vals = df_window['frost'].values if 'frost' in df_window.columns else df_window['Frost(%)'].values
    
    frost_lag_1 = frost_vals[-2] if len(frost_vals) >= 2 else frost_vals[-1]
    frost_lag_5 = frost_vals[-6] if len(frost_vals) >= 6 else frost_vals[-1]
    frost_lag_10 = frost_vals[-11] if len(frost_vals) >= 11 else frost_vals[-1]
    frost_lag_30 = frost_vals[-31] if len(frost_vals) >= 31 else frost_vals[-1]
    frost_lag_60 = frost_vals[-61] if len(frost_vals) >= 61 else frost_vals[-1]
    
    # === 滚动统计 ===
    frost_rolling_mean_10 = np.mean(frost_vals[-min(10, len(frost_vals)):])
    frost_rolling_std_10 = np.std(frost_vals[-min(10, len(frost_vals)):])
    frost_rolling_mean_60 = np.mean(frost_vals[-min(60, len(frost_vals)):])
    
    temp_vals = df_window['temperature'].values if 'temperature' in df_window.columns else df_window['Temp(C)'].values
    temp_rolling_mean_10 = np.mean(temp_vals[-min(10, len(temp_vals)):])
    
    # === 差分特征 ===
    frost_diff = frost_vals[-1] - frost_vals[-2] if len(frost_vals) >= 2 else 0
    frost_diff_5 = frost_vals[-1] - frost_vals[-6] if len(frost_vals) >= 6 else 0
    temp_diff = temp_vals[-1] - temp_vals[-2] if len(temp_vals) >= 2 else 0
    
    # 映射列名（兼容多种命名）
    temp = row.get('temperature', row.get('Temp(C)', 0))
    outdoor = row.get('outdoor', row.get('Outdoor(C)', 0))
    humidity = row.get('humidity', row.get('Humidity(%)', 0))
    energy = row.get('energy', row.get('Energy(kW)', 0))
    current = row.get('current', row.get('Current(A)', 0))
    comp = int(row.get('comp', row.get('Comp', 1)))
    fan = int(row.get('fan', row.get('Fan', 1)))
    door = int(row.get('door', row.get('Door', 0)))
    frost = row.get('frost', row.get('Frost(%)', 0))
    
    # 构建特征向量（顺序必须与训练时一致）
    features = {
        'Temp(C)': temp,
        'Outdoor(C)': outdoor,
        'Humidity(%)': humidity,
        'Energy(kW)': energy,
        'Current(A)': current,
        'Comp': comp,
        'Fan': fan,
        'Door': door,
        'hour': hour,
        'minute': minute,
        'dayofweek': dayofweek,
        'day': day,
        'hour_sin': hour_sin,
        'hour_cos': hour_cos,
        'day_sin': day_sin,
        'day_cos': day_cos,
        'Frost_lag_1': frost_lag_1,
        'Frost_lag_5': frost_lag_5,
        'Frost_lag_10': frost_lag_10,
        'Frost_lag_30': frost_lag_30,
        'Frost_lag_60': frost_lag_60,
        'Frost_rolling_mean_10': frost_rolling_mean_10,
        'Frost_rolling_std_10': frost_rolling_std_10,
        'Frost_rolling_mean_60': frost_rolling_mean_60,
        'Temp_rolling_mean_10': temp_rolling_mean_10,
        'Frost_diff': frost_diff,
        'Frost_diff_5': frost_diff_5,
        'Temp_diff': temp_diff
    }
    
    return features


def predict_frost(current_data, history_data):
    """
    预测结霜率
    
    Args:
        current_data: 当前数据字典
        history_data: 历史数据列表（每项为字典）
    
    Returns:
        dict: 预测结果，包含预测值、置信区间、趋势判断
    """
    if not load_model():
        return None
    
    # 构建DataFrame
    df_all = pd.DataFrame(history_data + [current_data])
    
    # 计算特征
    features = compute_features(df_all)
    if features is None:
        return None
    
    # 按训练顺序提取特征值
    X = pd.DataFrame([features])[_feature_cols]
    
    # 预测
    frost_pred = _model.predict(X)[0]
    frost_pred = max(0, min(100, frost_pred))  # 限制在0-100范围
    
    # === 趋势分析 ===
    frost_history = df_all['frost'].values[-min(60, len(df_all)):] if 'frost' in df_all.columns else []
    
    trend = 'stable'
    trend_icon = '➡️'
    trend_desc = '结霜率稳定'
    trend_color = '#4ecdc4'
    
    if len(frost_history) >= 5:
        recent = np.mean(frost_history[-5:])
        older = np.mean(frost_history[-10:-5]) if len(frost_history) >= 10 else np.mean(frost_history[:-5])
        diff = recent - older
        
        if diff > 2:
            trend = 'rising'
            trend_icon = '📈'
            trend_desc = '结霜率上升中'
            trend_color = '#ff6b6b'
        elif diff < -2:
            trend = 'falling'
            trend_icon = '📉'
            trend_desc = '结霜率下降中'
            trend_color = '#4ecdc4'
    
    # === 除霜时机判断 ===
    defrost_advice = '暂不需除霜'
    defrost_icon = '✅'
    defrost_color = '#28a745'
    
    if frost_pred >= 85:
        defrost_advice = '建议立即除霜'
        defrost_icon = '🚨'
        defrost_color = '#dc3545'
    elif frost_pred >= 70:
        defrost_advice = '建议近期除霜'
        defrost_icon = '⚠️'
        defrost_color = '#ffc107'
    elif frost_pred >= 50:
        defrost_advice = '关注结霜趋势'
        defrost_icon = '👀'
        defrost_color = '#17a2b8'
    
    # === 变化率分析 ===
    change_rate = 0
    if len(frost_history) >= 2:
        change_rate = (frost_history[-1] - frost_history[0]) / len(frost_history) * 60  # 每小时变化率
    
    # === 预测未来趋势（简单线性外推）===
    future_trend = 'stable'
    if len(frost_history) >= 10:
        recent_trend = (frost_history[-1] - frost_history[-10]) / 9  # 平均每步变化
        remaining_capacity = 100 - frost_pred  # 剩余容量
        if remaining_capacity > 0 and recent_trend > 0.1:
            hours_to_full = remaining_capacity / (recent_trend * 60) if recent_trend > 0 else float('inf')
            future_trend = f"预计 {hours_to_full:.1f} 小时后结霜率达到100%"
        elif recent_trend < -0.1:
            future_trend = "结霜率持续下降，除霜效果良好"
        else:
            future_trend = "结霜率趋于平稳"
    
    return {
        'frost_pred': round(frost_pred, 2),
        'frost_actual': round(current_data.get('frost', current_data.get('Frost(%)', 0)), 2),
        'trend': trend,
        'trend_icon': trend_icon,
        'trend_desc': trend_desc,
        'trend_color': trend_color,
        'defrost_advice': defrost_advice,
        'defrost_icon': defrost_icon,
        'defrost_color': defrost_color,
        'change_rate': round(change_rate, 3),
        'future_trend': future_trend,
        'confidence': 'high' if len(history_data) >= 60 else ('medium' if len(history_data) >= 10 else 'low'),
        'model_ready': True
    }


def get_feature_importance():
    """获取特征重要性"""
    if not load_model():
        return None
    
    imp = pd.DataFrame({
        'feature': _feature_cols,
        'importance': _model.feature_importance()
    }).sort_values('importance', ascending=False)
    
    return imp.head(10).to_dict('records')
