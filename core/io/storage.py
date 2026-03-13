import os
import time
import datetime
import json
import configparser
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ── 1. Load Settings ─────────────────────────────────────────────────────────
config = configparser.ConfigParser()
config.read('settings.ini')

# The Chunk Size determines how many frames we keep in RAM before writing to the Hard Drive.
# If this is 1, the app will stutter because saving to a Hard Drive is slow.
# If this is 10,000, you will lose a lot of data if the app crashes before saving.
# 100 is the perfect balance.
CHUNK_SIZE = int(config.get('Recording', 'chunk_size', fallback=100))

# ─────────────────────────────────────────────────────────────────────────────
#  Camera Storage (MediaPipe 3D Coordinates)
# ─────────────────────────────────────────────────────────────────────────────
class CameraSessionWriter:
    """
    Saves the 3D X/Y/Z coordinates of the 33 human joints to a Parquet file.
    """
    def __init__(self, s, a, metadata=None):
        os.makedirs("records", exist_ok=True)
        self.subject_id = s
        self.activity = a
        self.metadata = metadata or {}
        
        # Generate a unique filename using the current time
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = f"records/{s}_{a}_{timestamp}.parquet"
        
        self.data_buffer = []
        self.chunk_size = CHUNK_SIZE
        self.writer = None
        self.total_frames = 0
        
        # Pre-build the column headers: [timestamp, j0_x, j0_y, j0_z, j1_x...]
        self.schema_columns = ['timestamp']
        for i in range(33):
            self.schema_columns.extend([f"j{i}_x", f"j{i}_y", f"j{i}_z"])

    def write_frame(self, frame_data: dict):
        """Called 30 times a second by the publisher stream."""
        self.data_buffer.append(frame_data)
        self.total_frames += 1
        
        # When the RAM buffer gets full, dump it to the Hard Drive
        if len(self.data_buffer) >= self.chunk_size:
            self._flush_buffer()

    def _flush_buffer(self):
        """Converts the RAM buffer into a Parquet table and writes to disk."""
        if not self.data_buffer: return
            
        # Convert dictionaries to a Pandas DataFrame
        df = pd.DataFrame(self.data_buffer, columns=self.schema_columns)
        table = pa.Table.from_pandas(df)
        
        # If this is the very first chunk, we need to create the file and embed the Metadata
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
            
            # Open the file
            self.writer = pq.ParquetWriter(self.filepath, schema_with_meta)
            
        # Append the chunk to the file
        self.writer.write_table(table)
        
        # Clear the RAM buffer so it doesn't grow infinitely
        self.data_buffer.clear()

    def close(self):
        """Called when the user stops the recording. Ensures the final few frames are saved."""
        self._flush_buffer()
        if self.writer:
            self.writer.close()
            print(f"✅ Camera Session saved: {self.filepath} ({self.total_frames} frames)")
        else:
            print("No camera data recorded.")

# ─────────────────────────────────────────────────────────────────────────────
#  Radar Storage (Raw Byte Arrays)
# ─────────────────────────────────────────────────────────────────────────────
class RadarSessionWriter:
    """
    Saves the raw, hexadecimal byte matrices from the TI Radar to a Parquet file.
    Because these arrays are massive, writing them in chunks is extremely important.
    """
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
        """Saves the current timestamp and the raw bytes of the radar matrix."""
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
    """Saves a Pandas DataFrame to a standard CSV file."""
    try:
        df.to_csv(filepath, index=False)
        return True, f"Successfully saved to {os.path.basename(filepath)}"
    except Exception as e:
        return False, f"Export failed: {str(e)}"
    
def load_session_data(filepath: str):
    """
    The master loading function. 
    Reads a Parquet or CSV file into memory and automatically downcasts 
    64-bit floats to 32-bit floats to instantly cut RAM usage in half!
    """
    subj, act = "Unknown", "Unknown"
    
    if filepath.endswith('.parquet'):
        # 1. Read the embedded Metadata to figure out who the subject was
        schema = pq.read_schema(filepath)
        if schema.metadata:
            if b'subject_id' in schema.metadata:
                subj = schema.metadata[b'subject_id'].decode()
            if b'activity' in schema.metadata:
                act = schema.metadata[b'activity'].decode()
                
        # 2. Read the actual data. (Pandas uses PyArrow natively for Parquet)
        df = pd.read_parquet(filepath)
        
    elif filepath.endswith('.csv'):
        # Try to use PyArrow for CSVs because it's much faster than NumPy, 
        # but fallback to standard Pandas if it fails.
        try:
            df = pd.read_csv(filepath, engine='pyarrow')
        except:
            df = pd.read_csv(filepath)
            
        # Extract the subject/activity from the filename if possible (e.g. John_Running_clean.csv)
        clean_name = os.path.basename(filepath).replace('.csv', '')
        parts = clean_name.split('_')
        if len(parts) >= 2:
            subj, act = parts[0], parts[1]
    else:
        raise ValueError(f"Unsupported file format: {filepath}")

    # OPTIMIZATION: Convert massive 64-bit floats down to 32-bit.
    # A human joint moving 0.0001 meters does not require 64 decimals of precision.
    # This immediately cuts memory consumption by 50%.
    float_cols = df.select_dtypes(include=['float64']).columns
    if len(float_cols) > 0:
        df[float_cols] = df[float_cols].astype('float32')

    return df, subj, act

def export_analysis_results(df_timeseries, df_stats, base_filepath):
    """Exports both the timeseries angles and the summary statistics (Mean/Min/Max)."""
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