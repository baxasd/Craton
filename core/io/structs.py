import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from datetime import datetime

# ================================================
# MEDIAPIPE CONSTANTS
# ================================================
# Google's MediaPipe AI returns a raw list of 33 points. 
# This dictionary maps the arbitrary array index to actual anatomical names.
POSE_LANDMARKS = {
    0: "nose", 1: "left_eye_inner", 2: "left_eye", 3: "left_eye_outer",
    4: "right_eye_inner", 5: "right_eye", 6: "right_eye_outer", 7: "left_ear",
    8: "right_ear", 9: "mouth_left", 10: "mouth_right", 11: "left_shoulder",
    12: "right_shoulder", 13: "left_elbow", 14: "right_elbow", 15: "left_wrist",
    16: "right_wrist", 17: "left_pinky", 18: "right_pinky", 19: "left_index",
    20: "right_index", 21: "left_thumb", 22: "right_thumb", 23: "left_hip",
    24: "right_hip", 25: "left_knee", 26: "right_knee", 27: "left_ankle",
    28: "right_ankle", 29: "left_heel", 30: "right_heel", 31: "left_foot_index",
    32: "right_foot_index"
}

# Reverse mapping (e.g., NAME_TO_ID['left_knee'] returns 25)
NAME_TO_ID = {v: k for k, v in POSE_LANDMARKS.items()}

def identify_joint_columns(columns: List[str]) -> List[str]:
    """
    Scans a DataFrame's columns and finds the X-coordinates of joints.
    Handles multiple naming conventions (e.g., 'j0_x' or 'joint_0_x').
    """
    return [c for c in columns if c.endswith('_x') and (c.startswith('j') or c.startswith('joint'))]

# ================================================
# Core Data Structures
# ================================================

@dataclass
class Joint:
    """Represents a single human joint in 3D space at a specific millisecond in time."""
    name: str = "unknown"
    pixel: Tuple[int, int] = (0, 0)       
    metric: Tuple[float, float, float] = (0.0, 0.0, 0.0) # (X, Y, Z) in real-world meters
    visibility: float = 0.0

@dataclass
class Frame:
    """Represents a single snapshot in time, holding up to 33 Joints."""
    timestamp: float
    frame_id: int
    joints: Dict[int, Joint] = field(default_factory=dict) 

@dataclass
class Session:
    """Represents an entire recording (a collection of thousands of Frames)."""
    subject_id: str = "Anonymous"
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    frames: List[Frame] = field(default_factory=list)

    @property
    def fps(self):
        """Calculates the true framerate based on actual elapsed timestamps."""
        if len(self.frames) < 2: return 30.0
        dur = self.frames[-1].timestamp - self.frames[0].timestamp
        return len(self.frames) / dur if dur > 0 else 30.0

    @property
    def duration(self):
        """Total time of the recording in seconds."""
        if not self.frames: return 0.0
        return self.frames[-1].timestamp - self.frames[0].timestamp

# ================================================
# Converters
# ================================================

def session_to_df(session: Session) -> pd.DataFrame:
    """
    Converts a hierarchical Session Object back into a flat Pandas DataFrame.
    Useful if you want to modify a Session and then save it back to disk.
    """
    rows = []
    for f in session.frames:
        row = {'timestamp': f.timestamp, 'frame': f.frame_id}
        for j_idx, joint in f.joints.items():
            row[f'j{j_idx}_x'] = joint.metric[0]
            row[f'j{j_idx}_y'] = joint.metric[1]
            row[f'j{j_idx}_z'] = joint.metric[2]
        rows.append(row)
        
    return pd.DataFrame(rows)

def df_to_session(df: pd.DataFrame) -> Session:
    """
    Converts a flat Pandas DataFrame into a hierarchical Session Object.
    Required to feed recorded data into the 3D Visualizer.
    """
    sess = Session(subject_id="Processed", date=str(pd.Timestamp.now()))
    if df.empty: return sess
    
    x_cols = identify_joint_columns(df.columns)
    start_time = None
    
    # OPTIMIZATION: df.to_dict('records') is exponentially faster than df.iterrows()
    # It converts the DataFrame to native Python dictionaries instantly in C.
    records = df.to_dict('records')

    # Pre-parse exactly what prefixes and names we are looking for to avoid string parsing in the loop
    parsed_columns = []
    for col in x_cols:
        prefix = col[:-2] # e.g., 'j0_x' becomes 'j0'
        idx = int(prefix.split('_')[1]) if 'joint_' in prefix else int(prefix[1:])
        real_name = POSE_LANDMARKS.get(idx, str(idx))
        parsed_columns.append((prefix, idx, real_name))

    for i, row in enumerate(records):
        # 1. Calculate Relative Timestamp (Force the first frame to equal 0.0 seconds)
        raw_ts = row.get('timestamp', 0.0)
        ts = 0.0
        
        try:
            if isinstance(raw_ts, str):
                dt = datetime.fromisoformat(raw_ts)
                if start_time is None: start_time = dt
                ts = (dt - start_time).total_seconds()
            else:
                raw_val = float(raw_ts)
                if start_time is None: start_time = raw_val
                ts = raw_val - start_time
        except Exception:
            # Fallback: Assume exactly 30fps if timestamps are completely corrupted
            ts = float(i) * 0.033 

        f = Frame(timestamp=ts, frame_id=int(i))
        
        # 2. Extract 3D Coordinates for all 33 joints
        for prefix, idx, real_name in parsed_columns:
            # .get() is fast and won't crash if a column goes missing for a frame
            mx = float(row.get(f'{prefix}_x', 0.0))
            my = float(row.get(f'{prefix}_y', 0.0))
            mz = float(row.get(f'{prefix}_z', 0.0))
            
            f.joints[idx] = Joint(name=real_name, metric=(mx, my, mz))
            
        sess.frames.append(f)
        
    return sess