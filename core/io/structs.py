import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from datetime import datetime

# ================================================
# MEDIAPIPE CONSTANTS
# ================================================
POSE_LANDMARKS = {
    0: "nose",
    1: "left_eye_inner",
    2: "left_eye",
    3: "left_eye_outer",
    4: "right_eye_inner",
    5: "right_eye",
    6: "right_eye_outer",
    7: "left_ear",
    8: "right_ear",
    9: "mouth_left",
    10: "mouth_right",
    11: "left_shoulder",
    12: "right_shoulder",
    13: "left_elbow",
    14: "right_elbow",
    15: "left_wrist",
    16: "right_wrist",
    17: "left_pinky",
    18: "right_pinky",
    19: "left_index",
    20: "right_index",
    21: "left_thumb",
    22: "right_thumb",
    23: "left_hip",
    24: "right_hip",
    25: "left_knee",
    26: "right_knee",
    27: "left_ankle",
    28: "right_ankle",
    29: "left_heel",
    30: "right_heel",
    31: "left_foot_index",
    32: "right_foot_index",
}

# ── 1. Skeleton Configuration (From render.py) ──
VISIBLE_NAMES = [
    "nose",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "hip_mid",
    "shoulder_mid",  # Added so the spine dots draw
]

BONES_LIST = [
    ("hip_mid", "shoulder_mid"),  # Spine
    ("hip_mid", "left_hip"),  # Pelvis L
    ("hip_mid", "right_hip"),  # Pelvis R
    ("shoulder_mid", "left_shoulder"),  # Clavicle L
    ("shoulder_mid", "right_shoulder"),  # Clavicle R
    ("left_shoulder", "left_elbow"),  # Arm L
    ("left_elbow", "left_wrist"),  # Forearm L
    ("right_shoulder", "right_elbow"),  # Arm R
    ("right_elbow", "right_wrist"),  # Forearm R
    ("left_hip", "left_knee"),  # Thigh L
    ("left_knee", "left_ankle"),  # Shin L
    ("right_hip", "right_knee"),  # Thigh R
    ("right_knee", "right_ankle"),  # Shin R
    ("shoulder_mid", "nose"),  # Neck
]

NAME_TO_ID = {v: k for k, v in POSE_LANDMARKS.items()}


def identify_joint_columns(columns: List[str]) -> List[str]:
    return [
        c
        for c in columns
        if c.endswith("_x") and (c.startswith("j") or c.startswith("joint"))
    ]


# ================================================
# Core Data Structures
# ================================================


@dataclass
class Joint:
    name: str = "unknown"
    pixel: Tuple[int, int] = (0, 0)
    metric: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    visibility: float = 0.0


@dataclass
class Frame:
    timestamp: float
    frame_id: int
    joints: Dict[int, Joint] = field(default_factory=dict)


@dataclass
class Session:
    subject_id: str = "Anonymous"
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    frames: List[Frame] = field(default_factory=list)

    @property
    def fps(self):
        if len(self.frames) < 2:
            return 30.0
        dur = self.duration
        # Prevent divide-by-zero if timestamps are corrupted
        return len(self.frames) / dur if dur > 0.001 else 30.0

    @property
    def duration(self):
        if not self.frames:
            return 0.0
        return self.frames[-1].timestamp - self.frames[0].timestamp


# ================================================
# Converters
# ================================================


def df_to_session(df: pd.DataFrame) -> Session:
    # Notice we removed pd.Timestamp.now(). The dataclass default_factory handles the date automatically!
    sess = Session(subject_id="Processed")
    if df.empty:
        return sess

    x_cols = identify_joint_columns(df.columns)
    start_time = None

    records = df.to_dict("records")

    parsed_columns = []
    for col in x_cols:
        prefix = col[:-2]
        idx = int(prefix.split("_")[1]) if "joint_" in prefix else int(prefix[1:])
        real_name = POSE_LANDMARKS.get(idx, str(idx))
        parsed_columns.append((prefix, idx, real_name))

    for i, row in enumerate(records):
        # Safely grab the timestamp regardless of how Pandas formatted the column name
        raw_ts = row.get("timestamp") or row.get("Timestamp") or row.get("time") or 0.0
        ts = 0.0

        try:
            # FIX: If it is already a raw float (Unix epoch), do math normally
            if isinstance(raw_ts, (int, float)):
                if start_time is None:
                    start_time = float(raw_ts)
                ts = float(raw_ts) - start_time
            # FIX: If it is a string OR a pd.Timestamp object, let Pandas safely extract the seconds
            else:
                dt = pd.to_datetime(raw_ts)
                if start_time is None:
                    start_time = dt
                ts = (dt - start_time).total_seconds()

        except Exception as e:
            # We only hit this fallback if the data is genuinely missing/corrupted
            ts = float(i) * 0.033

        f = Frame(timestamp=ts, frame_id=int(i))

        for prefix, idx, real_name in parsed_columns:
            mx = float(row.get(f"{prefix}_x", 0.0))
            my = float(row.get(f"{prefix}_y", 0.0))
            mz = float(row.get(f"{prefix}_z", 0.0))

            f.joints[idx] = Joint(name=real_name, metric=(mx, my, mz))

        sess.frames.append(f)

    return sess
