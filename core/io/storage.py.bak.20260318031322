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
CHUNK_SIZE = int(config.get('Recording', 'chunk_size', fallback=100))

# ─────────────────────────────────────────────────────────────────────────────
#  Camera Storage
# ─────────────────────────────────────────────────────────────────────────────
class CameraSessionWriter:
    """
    Saves the 3D X/Y/Z coordinates of the 33 human joints to a Parquet file.
    """
    def __init__(self, metadata=None):
        os.makedirs("records", exist_ok=True)
        self.metadata = metadata or {}
        
        # Generate a unique filename using the current time
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = f"records/camera_{timestamp}.parquet"
        
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
            print(f"Camera Session saved: {self.total_frames} frames")
        else:
            print("No camera data recorded.")

# ─────────────────────────────────────────────────────────────────────────────
#  Radar Storage (Raw Byte Arrays)
# ─────────────────────────────────────────────────────────────────────────────
class RadarSessionWriter:
    """
    Saves the raw, hexadecimal byte matrices from the TI Radar to a Parquet file.
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
            print(f"Radar Session saved: {self.total_frames} frames")