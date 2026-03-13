import numpy as np
import pandas as pd
from core.io.structs import Frame, NAME_TO_ID

# ── 1. Vector Extraction Helpers ─────────────────────────────────────────────

def _get_vec(frame: Frame, name_or_id):
    """
    Extracts the 3D coordinate of a specific joint from a Frame object.
    Returns it as a fast NumPy array for vector math.
    """
    idx = name_or_id
    
    # Allow the user to request a joint by string name (e.g., "left_knee") or integer ID (25)
    if isinstance(name_or_id, str):
        idx = NAME_TO_ID.get(name_or_id)
    
    # Safety Check: If the joint wasn't found by the AI in this frame, abort gracefully
    if idx is None or idx not in frame.joints:
        return None
    
    j = frame.joints[idx]
    
    # Return the Metric (Real-world meters), not the Pixel coordinates
    return np.array([j.metric[0], j.metric[1], j.metric[2]])


def _get_trunk_midpoints(f: Frame):
    """
    OPTIMIZATION: Helper function that calculates the center of the hips and 
    center of the shoulders. Used for drawing the skeleton and calculating lean.
    Saves us from calculating this 3 separate times per frame!
    """
    rh = _get_vec(f, "right_hip")
    lh = _get_vec(f, "left_hip")
    rs = _get_vec(f, "right_shoulder")
    ls = _get_vec(f, "left_shoulder")

    # If the camera lost track of ANY of these 4 critical points, we can't calculate the trunk.
    if any(v is None for v in [rh, lh, rs, ls]): 
        return None, None

    # Find the exact center point between the left and right sides
    mid_hip = (rh + lh) / 2.0
    mid_shoulder = (rs + ls) / 2.0
    
    return mid_hip, mid_shoulder


def get_point(f: Frame, name: str):
    """
    Returns a 2D (X, Y) tuple. Used primarily by the 3D Visualizer Tab 
    to center the camera on the runner's body.
    """
    if name in ["hip_mid", "shoulder_mid"]:
        mid_hip, mid_shoulder = _get_trunk_midpoints(f)
        if mid_hip is None: return None
        
        vec = mid_hip if name == "hip_mid" else mid_shoulder
        return (float(vec[0]), float(vec[1]))
    else:
        v = _get_vec(f, name)
        if v is not None:
            return (float(v[0]), float(v[1]))
    return None

# ── 2. Biomechanical Angle Calculations ──────────────────────────────────────

def calculate_joint_angle(f: Frame, p1: str, p2: str, p3: str) -> float:
    """
    Calculates the 3D angle at the middle point (p2) created by lines from p1 and p3.
    Example: To get the Knee angle, p1=Hip, p2=Knee, p3=Ankle.
    """
    a = _get_vec(f, p1)
    b = _get_vec(f, p2)
    c = _get_vec(f, p3)

    if a is None or b is None or c is None: return 0.0

    # Create vectors pointing FROM the middle joint (b) TO the outer joints (a, c)
    ba = a - b
    bc = c - b

    # Calculate the length (magnitude) of those vectors
    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    
    # Prevent divide-by-zero errors if the joints perfectly overlap
    if norm_ba == 0 or norm_bc == 0: return 0.0

    # Dot Product Formula: A·B = |A||B|cos(θ)
    cosine_angle = np.dot(ba, bc) / (norm_ba * norm_bc)
    
    # Clip prevents floating point rounding errors (like 1.0000000002) from crashing arccos
    angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))

    return float(np.degrees(angle))


def calculate_frontal_lean(f: Frame) -> float:
    """Calculates Side-to-Side Lean (X-Y plane)."""
    mid_hip, mid_shoulder = _get_trunk_midpoints(f)
    if mid_hip is None: return 0.0

    # X (horizontal) and Y (vertical) difference between hips and shoulders
    dx = mid_shoulder[0] - mid_hip[0]
    dy = mid_shoulder[1] - mid_hip[1]
    
    # Use arctan2 to get the angle relative to the vertical axis.
    # Note: -dy is used because image coordinates have Y=0 at the TOP of the screen!
    return float(np.degrees(np.arctan2(dx, -dy)))


def calculate_sagittal_lean(f: Frame) -> float:
    """Calculates Forward/Backward Lean (Z-Y plane)."""
    mid_hip, mid_shoulder = _get_trunk_midpoints(f)
    if mid_hip is None: return 0.0

    # Z (depth) and Y (vertical) difference
    dz = mid_shoulder[2] - mid_hip[2]
    dy = mid_shoulder[1] - mid_hip[1]
    
    return float(np.degrees(np.arctan2(dz, -dy)))


# ── 3. Pipeline Aggregation ──────────────────────────────────────────────────

def compute_all_metrics(f: Frame) -> dict:
    """Calculates all 8 core postural metrics for a single frame."""
    return {
        'lean_x': calculate_frontal_lean(f),   # Side-to-side
        'lean_z': calculate_sagittal_lean(f),  # Forward/Back
        
        'l_knee': calculate_joint_angle(f, "left_hip", "left_knee", "left_ankle"),
        'r_knee': calculate_joint_angle(f, "right_hip", "right_knee", "right_ankle"),
        
        'l_hip':  calculate_joint_angle(f, "left_shoulder", "left_hip", "left_knee"),
        'r_hip':  calculate_joint_angle(f, "right_shoulder", "right_hip", "right_knee"),
        
        'l_sho':  calculate_joint_angle(f, "left_hip", "left_shoulder", "left_elbow"),
        'r_sho':  calculate_joint_angle(f, "right_hip", "right_shoulder", "right_elbow"),
        
        'l_elb':  calculate_joint_angle(f, "left_shoulder", "left_elbow", "left_wrist"),
        'r_elb':  calculate_joint_angle(f, "right_shoulder", "right_elbow", "right_wrist")
    }

def generate_analysis_report(session):
    """
    Loops through all frames, computes the physics, and returns:
    1. A full Timeseries DataFrame (every angle at every frame)
    2. A Summary Statistics DataFrame (Mean, Median, Std, etc.)
    """
    data = []
    for f in session.frames:
        metrics_dict = compute_all_metrics(f)
        metrics_dict['timestamp'] = f.timestamp
        metrics_dict['frame'] = f.frame_id
        data.append(metrics_dict)
    
    # Create the full Line-Graph timeseries dataset
    df_timeseries = pd.DataFrame(data)
    
    # Reorder columns to strictly ensure timestamp and frame are first
    cols = ['timestamp', 'frame'] + [c for c in df_timeseries.columns if c not in ['timestamp', 'frame']]
    df_timeseries = df_timeseries[cols]
    
    # Automatically calculate count, mean, std, min, 25%, 50% (median), 75%, and max
    # We drop timestamp and frame from this calculation because the "average timestamp" is meaningless data.
    df_stats = df_timeseries.drop(columns=['timestamp', 'frame']).describe()
    
    return df_timeseries, df_stats