import numpy as np
import pandas as pd
from src.data.types import Frame, NAME_TO_ID

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
    Helper function that calculates the center of the hips and 
    center of the shoulders. Used for drawing the skeleton and calculating X-lean.
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
    Includes normalization to ensure the angle represents 'Flexion' (0-180).
    """
    a = _get_vec(f, p1)
    b = _get_vec(f, p2)
    c = _get_vec(f, p3)

    if a is None or b is None or c is None: return 0.0

    # Create vectors pointing FROM the middle joint (b) TO the outer joints (a, c)
    ba = a - b
    bc = c - b

    # Normalize vectors for stable dot product
    norm_a = np.linalg.norm(ba)
    norm_c = np.linalg.norm(bc)
    
    if norm_a < 1e-4 or norm_c < 1e-4: return 0.0

    # Dot Product Formula for 3D Angle
    cosine_angle = np.dot(ba, bc) / (norm_a * norm_c)
    angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))

    return float(np.degrees(angle))


def calculate_trunk_lean(f: Frame) -> tuple[float, float]:
    """
    Calculates Trunk Lean using 2D Projections (X-Y Plane).
    This avoids the flickering Z-axis (depth) issues of the RealSense camera.
    
    Optimized: Averages the lean of the left side, right side, and midline 
    to create a 'Stable 2D' estimate that is resistant to limb occlusion.
    """
    # 1. Midline Vector
    mid_hip, mid_shoulder = _get_trunk_midpoints(f)
    
    # 2. Left Side Vector
    lh = _get_vec(f, "left_hip")
    ls = _get_vec(f, "left_shoulder")
    
    # 3. Right Side Vector
    rh = _get_vec(f, "right_hip")
    rs = _get_vec(f, "right_shoulder")
    
    leans = []
    
    # We calculate the angle for each available pair and average them.
    # This acts as a hardware-level 'noise filter'
    for p_hip, p_sho in [(mid_hip, mid_shoulder), (lh, ls), (rh, rs)]:
        if p_hip is not None and p_sho is not None:
            dx = p_sho[0] - p_hip[0]
            dy = p_sho[1] - p_hip[1]
            # Use negative dy because MediaPipe Y is inverted
            leans.append(np.degrees(np.arctan2(dx, -dy)))
            
    if not leans: return 0.0, 0.0
    
    stable_lean_x = float(np.mean(leans))
    
    # Sagittal Lean (Z-Y) is kept as a secondary metric but flagged as 
    # 'Noisy' in the UI/Stats. We only use the midline for this.
    stable_lean_z = 0.0
    if mid_hip is not None and mid_shoulder is not None:
        dz = mid_shoulder[2] - mid_hip[2]
        dy = mid_shoulder[1] - mid_hip[1]
        stable_lean_z = float(np.degrees(np.arctan2(dz, -dy)))
        
    return stable_lean_x, stable_lean_z


# ── 3. Pipeline Aggregation ──────────────────────────────────────────────────

def compute_all_metrics(f: Frame) -> dict:
    """Calculates all core postural metrics for a single frame."""
    lean_x, lean_z = calculate_trunk_lean(f)
    
    metrics = {
        'lean_x': lean_x,   # Stable 2D (Side-to-Side)
        'lean_z': lean_z,   # Depth-based (Forward/Back) - Noisy
        
        'l_knee': calculate_joint_angle(f, "left_hip", "left_knee", "left_ankle"),
        'r_knee': calculate_joint_angle(f, "right_hip", "right_knee", "right_ankle"),
        
        'l_hip':  calculate_joint_angle(f, "left_shoulder", "left_hip", "left_knee"),
        'r_hip':  calculate_joint_angle(f, "right_shoulder", "right_hip", "right_knee"),
        
        'l_sho':  calculate_joint_angle(f, "left_hip", "left_shoulder", "left_elbow"),
        'r_sho':  calculate_joint_angle(f, "right_hip", "right_shoulder", "right_elbow"),
        
        'l_elb':  calculate_joint_angle(f, "left_shoulder", "left_elbow", "left_wrist"),
        'r_elb':  calculate_joint_angle(f, "right_shoulder", "right_elbow", "right_wrist"),
        
        # Center of Mass proxy
        'com_y': _get_trunk_midpoints(f)[0][1] if _get_trunk_midpoints(f)[0] is not None else 0.0
    }
    
    # Symmetry Indices
    pairs = [('knee', 'l_knee', 'r_knee'), ('hip', 'l_hip', 'r_hip'), 
             ('sho', 'l_sho', 'r_sho'), ('elb', 'l_elb', 'r_elb')]
    
    for name, l_key, r_key in pairs:
        l_val, r_val = metrics[l_key], metrics[r_key]
        metrics[f'sym_{name}'] = 100.0 * (r_val - l_val) / (max(1.0, (l_val + r_val) / 2.0))
            
    return metrics

def calculate_session_trends(df: pd.DataFrame) -> dict:
    """
    Applies Linear Regression to key metrics to detect fatigue or form shifts.
    Returns a dictionary of slopes (units/minute).
    """
    trends = {}
    if len(df) < 60: return trends # Need at least 2 seconds of data
    
    # Convert time to minutes for readable slopes
    x = (df['timestamp'] - df['timestamp'].iloc[0]).values / 60.0
    
    cols_to_analyze = ['lean_x', 'lean_z', 'l_knee', 'r_knee', 'sym_knee', 'sym_hip', 'l_hip', 'r_hip', 'l_sho', 'r_sho']
    for col in cols_to_analyze:
        if col in df.columns:
            y = df[col].values
            # Filter NaNs for regression
            mask = ~np.isnan(y)
            if mask.sum() > 10:
                slope, _ = np.polyfit(x[mask], y[mask], 1)
                trends[f'trend_{col}_min'] = float(slope)
                
    return trends

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
    
    df_ts = pd.DataFrame(data)
    
    # Reorder columns
    cols = ['timestamp', 'frame'] + [c for c in df_ts.columns if c not in ['timestamp', 'frame']]
    df_ts = df_ts[cols]
    
    # Statistical Summary
    df_stats = df_ts.drop(columns=['timestamp', 'frame']).describe()
    
    # Add Session-level Trends
    trends = calculate_session_trends(df_ts)
    for k, v in trends.items():
        df_stats.loc['mean', k] = v
    
    return df_ts, df_stats