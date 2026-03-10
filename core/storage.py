import os
import time
import datetime
import json
import configparser
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ── Load Settings ─────────────────────────────────────────────────────────────
config = configparser.ConfigParser()
config.read('settings.ini')
CHUNK_SIZE = int(config.get('Recording', 'chunk_size', fallback=100))

# ─────────────────────────────────────────────────────────────────────────────
#  Camera Storage
# ─────────────────────────────────────────────────────────────────────────────
class CameraSessionWriter:
    def __init__(self, s, a, metadata=None):
        os.makedirs("records", exist_ok=True)
        self.subject_id = s
        self.activity = a
        self.metadata = metadata or {}
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = f"records/{s}_{a}_{timestamp}.parquet"
        
        self.data_buffer = []
        self.chunk_size = CHUNK_SIZE
        self.writer = None
        self.total_frames = 0
        
        self.schema_columns = ['timestamp']
        for i in range(33):
            self.schema_columns.extend([f"j{i}_x", f"j{i}_y", f"j{i}_z"])

    def write_frame(self, frame_data: dict):
        self.data_buffer.append(frame_data)
        self.total_frames += 1
        if len(self.data_buffer) >= self.chunk_size:
            self._flush_buffer()

    def _flush_buffer(self):
        if not self.data_buffer: return
            
        df = pd.DataFrame(self.data_buffer, columns=self.schema_columns)
        table = pa.Table.from_pandas(df)
        
        if self.writer is None:
            custom_meta = {
                b"subject_id": str(self.subject_id).encode(),
                b"activity": str(self.activity).encode(),
                b"session_meta": json.dumps(self.metadata).encode()
            }
            existing_meta = table.schema.metadata or {}
            combined_meta = {**existing_meta, **custom_meta}
            
            schema_with_meta = table.schema.with_metadata(combined_meta)
            table = table.cast(schema_with_meta)
            self.writer = pq.ParquetWriter(self.filepath, schema_with_meta)
            
        self.writer.write_table(table)
        self.data_buffer.clear()

    def close(self):
        self._flush_buffer()
        if self.writer:
            self.writer.close()
            print(f"✅ Camera Session saved: {self.filepath} ({self.total_frames} frames)")
        else:
            print("No camera data recorded.")

# ─────────────────────────────────────────────────────────────────────────────
#  Radar Storage
# ─────────────────────────────────────────────────────────────────────────────
class RadarSessionWriter:
    def __init__(self, metadata=None):
        os.makedirs("records", exist_ok=True)
        self.start_time_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = f"records/radar_session_{self.start_time_str}.parquet"
        
        self.metadata = metadata or {}
        self.metadata["session_start"] = self.start_time_str
        
        self.data_buffer = []
        self.chunk_size = CHUNK_SIZE
        self.writer = None
        self.total_frames = 0
        self.schema_columns = ['timestamp', 'rdhm_bytes']

    def write_frame(self, rdhm_array: np.ndarray):
        self.data_buffer.append({'timestamp': time.time(), 'rdhm_bytes': rdhm_array.tobytes()})
        self.total_frames += 1
        if len(self.data_buffer) >= self.chunk_size:
            self._flush_buffer()

    def _flush_buffer(self):
        if not self.data_buffer: return
        df = pd.DataFrame(self.data_buffer, columns=self.schema_columns)
        table = pa.Table.from_pandas(df)
        
        if self.writer is None:
            schema_with_meta = table.schema.with_metadata({b"session_meta": str(self.metadata).encode()})
            table = table.cast(schema_with_meta)
            self.writer = pq.ParquetWriter(self.filepath, schema_with_meta)
            
        self.writer.write_table(table)
        self.data_buffer.clear()

    def close(self):
        self._flush_buffer()
        if self.writer:
            self.writer.close()
            print(f"✅ Radar Session saved: {self.filepath} ({self.total_frames} frames)")

# ─────────────────────────────────────────────────────────────────────────────
#  Data Retrieval & Export
# ─────────────────────────────────────────────────────────────────────────────
def export_clean_csv(df: pd.DataFrame, filepath: str):
    try:
        df.to_csv(filepath, index=False)
        return True, f"Successfully saved to {os.path.basename(filepath)}"
    except Exception as e:
        return False, f"Export failed: {str(e)}"
    
def load_session_data(filepath: str):
    subj, act = "Unknown", "Unknown"
    if filepath.endswith('.parquet'):
        schema = pq.read_schema(filepath)
        if schema.metadata:
            if b'subject_id' in schema.metadata:
                subj = schema.metadata[b'subject_id'].decode()
            if b'activity' in schema.metadata:
                act = schema.metadata[b'activity'].decode()
        df = pd.read_parquet(filepath)
    elif filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
        clean_name = os.path.basename(filepath).replace('.csv', '')
        parts = clean_name.split('_')
        if len(parts) >= 2:
            subj, act = parts[0], parts[1]
    else:
        raise ValueError(f"Unsupported file format: {filepath}")
    return df, subj, act

def export_analysis_results(df_timeseries, df_stats, base_filepath):
    try:
        if base_filepath.endswith('.csv'):
            base_filepath = base_filepath[:-4]
        
        ts_path = f"{base_filepath}_timeseries.csv"
        stats_path = f"{base_filepath}_summary.csv"
        
        df_timeseries.to_csv(ts_path, index=False)
        df_stats.to_csv(stats_path, index=True) 
        
        return True, f"Exported Successfully:\n{os.path.basename(ts_path)}\n{os.path.basename(stats_path)}"
    except Exception as e:
        return False, f"Export failed: {str(e)}"