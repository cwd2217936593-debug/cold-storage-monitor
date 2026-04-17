"""
数据存储模块 - 支持CSV和Excel导出
"""

import csv
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


class DataStorage:
    """数据存储管理器"""
    
    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path(__file__).parent.parent / "data"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self._records: List[Dict] = []
        self._lock = threading.Lock()
        self._auto_save_timer: Optional[threading.Timer] = None
        self._save_interval = 60  # 秒
        
        # 当前文件路径
        self._current_file: Optional[Path] = None
        
    def add_record(self, data: Dict, timestamp: datetime = None):
        """添加一条数据记录"""
        if timestamp is None:
            timestamp = datetime.now()
            
        record = {
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            **data
        }
        
        with self._lock:
            self._records.append(record)
            
        # 检查内存记录数限制
        if len(self._records) > 10000:
            self._auto_save()
            
    def add_records_batch(self, records: List[Dict]):
        """批量添加记录"""
        with self._lock:
            for data in records:
                if isinstance(data.get('timestamp'), datetime):
                    data['timestamp'] = data['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
                elif 'timestamp' not in data:
                    data['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._records.append(data)
                
    def get_records(self, limit: int = None) -> List[Dict]:
        """获取记录"""
        with self._lock:
            if limit:
                return self._records[-limit:]
            return self._records.copy()
            
    def get_dataframe(self, limit: int = None) -> pd.DataFrame:
        """获取pandas DataFrame"""
        records = self.get_records(limit)
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)
        
    def set_auto_save(self, interval: int = 60):
        """设置自动保存间隔"""
        self._save_interval = interval
        
    def start_auto_save(self):
        """启动自动保存"""
        self._schedule_auto_save()
        
    def stop_auto_save(self):
        """停止自动保存"""
        if self._auto_save_timer:
            self._auto_save_timer.cancel()
            self._auto_save_timer = None
            
    def _schedule_auto_save(self):
        """安排下一次自动保存"""
        self._auto_save_timer = threading.Timer(self._save_interval, self._auto_save)
        self._auto_save_timer.daemon = True
        self._auto_save_timer.start()
        
    def _auto_save(self):
        """执行自动保存"""
        try:
            if self._records:
                self._current_file = self._get_new_filepath()
                self.save_to_csv(self._current_file)
                # 只保留最新的N条记录在内存中
                with self._lock:
                    self._records = self._records[-1000:]  # 保留最近1000条
        except Exception as e:
            print(f"自动保存失败: {e}")
        finally:
            self._schedule_auto_save()
            
    def _get_new_filepath(self) -> Path:
        """生成新的文件路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.base_dir / f"data_{timestamp}.csv"
        
    def save_to_csv(self, filepath: Path = None, append: bool = False) -> Path:
        """保存为CSV文件"""
        if filepath is None:
            filepath = self._get_new_filepath()
            
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        records = self.get_records()
        if not records:
            return filepath
            
        df = pd.DataFrame(records)
        
        if append and filepath.exists():
            df.to_csv(filepath, mode='a', header=False, index=False, encoding='utf-8-sig')
        else:
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
        return filepath
        
    def save_to_excel(self, filepath: Path = None, include_charts: bool = False) -> Path:
        """保存为Excel文件"""
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.base_dir / f"data_{timestamp}.xlsx"
            
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        records = self.get_records()
        if not records:
            return filepath
            
        df = pd.DataFrame(records)
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # 数据表
            df.to_excel(writer, sheet_name='数据', index=False)
            
            # 统计表
            if len(df) > 0:
                stats = self._calculate_statistics(df)
                stats_df = pd.DataFrame([stats])
                stats_df.to_excel(writer, sheet_name='统计', index=False)
                
        return filepath
        
    def _calculate_statistics(self, df: pd.DataFrame) -> Dict:
        """计算统计信息"""
        stats = {
            "记录总数": len(df),
            "开始时间": df['timestamp'].iloc[0] if 'timestamp' in df.columns else '',
            "结束时间": df['timestamp'].iloc[-1] if 'timestamp' in df.columns else '',
        }
        
        # 对数值列计算统计
        numeric_cols = df.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            if col != 'timestamp':
                stats[f'{col}_均值'] = df[col].mean()
                stats[f'{col}_最小'] = df[col].min()
                stats[f'{col}_最大'] = df[col].max()
                stats[f'{col}_标准差'] = df[col].std()
                
        return stats
        
    def export_selection(self, start_time: str, end_time: str, format: str = 'csv') -> Path:
        """导出指定时间范围的数据"""
        records = self.get_records()
        if not records:
            raise ValueError("没有可导出的数据")
            
        df = pd.DataFrame(records)
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            mask = (df['timestamp'] >= start_time) & (df['timestamp'] <= end_time)
            df = df[mask]
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if format == 'excel':
            filepath = self.base_dir / f"export_{timestamp}.xlsx"
            df.to_excel(filepath, index=False, engine='openpyxl')
        else:
            filepath = self.base_dir / f"export_{timestamp}.csv"
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
        return filepath
        
    def clear(self):
        """清空所有记录"""
        with self._lock:
            self._records.clear()
            
    def get_memory_usage(self) -> int:
        """获取内存中记录数"""
        with self._lock:
            return len(self._records)
            
    def load_from_csv(self, filepath: Path):
        """从CSV文件加载数据"""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")
            
        df = pd.read_csv(filepath, encoding='utf-8-sig')
        records = df.to_dict('records')
        
        with self._lock:
            self._records.extend(records)


class DataExporter:
    """数据导出工具"""
    
    @staticmethod
    def export_csv(df: pd.DataFrame, filepath: Path, append: bool = False):
        """导出CSV"""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        if append and filepath.exists():
            df.to_csv(filepath, mode='a', header=False, index=False, encoding='utf-8-sig')
        else:
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
    @staticmethod
    def export_excel(df: pd.DataFrame, filepath: Path, include_stats: bool = True):
        """导出Excel"""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='数据', index=False)
            
            if include_stats and len(df) > 0:
                stats = df.describe().transpose()
                stats.to_excel(writer, sheet_name='统计')
                
    @staticmethod
    def export_json(df: pd.DataFrame, filepath: Path):
        """导出JSON"""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        df.to_json(filepath, orient='records', date_format='iso', force_ascii=False, indent=2)
