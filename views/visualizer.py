import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io

from core.io import structs
from core.math import kinematics

# ── 1. Skeleton Configuration (From render.py) ──
VISIBLE_NAMES = [
    "nose", 
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow", 
    "left_wrist", "right_wrist",
    "left_hip", "right_hip", 
    "left_knee", "right_knee", 
    "left_ankle", "right_ankle",
    "hip_mid", "shoulder_mid" # Added so the spine dots draw
]

BONES_LIST = [
    ("hip_mid", "shoulder_mid"),         # Spine
    ("hip_mid", "left_hip"),             # Pelvis L
    ("hip_mid", "right_hip"),            # Pelvis R
    ("shoulder_mid", "left_shoulder"),   # Clavicle L
    ("shoulder_mid", "right_shoulder"),  # Clavicle R
    
    ("left_shoulder", "left_elbow"),     # Arm L
    ("left_elbow", "left_wrist"),        # Forearm L
    ("right_shoulder", "right_elbow"),   # Arm R
    ("right_elbow", "right_wrist"),      # Forearm R
    
    ("left_hip", "left_knee"),           # Thigh L
    ("left_knee", "left_ankle"),         # Shin L
    ("right_hip", "right_knee"),         # Thigh R
    ("right_knee", "right_ankle"),       # Shin R
    
    ("shoulder_mid", "nose")             # Neck
]

@st.cache_data(show_spinner=False)
def load_session_for_viz(file_bytes, filename):
    """Loads the file directly from RAM into a hierarchical Session object."""
    buffer = io.BytesIO(file_bytes)
    if filename.endswith('.parquet'): df = pd.read_parquet(buffer)
    else: df = pd.read_csv(buffer)
    return structs.df_to_session(df)

def draw_2d_skeleton(frame):
    """Hardware-accelerated 2D projection of the 3D skeleton."""
    fig = go.Figure()
    
    # ── DRAW BONES ──
    for (n1, n2) in BONES_LIST:
        p1 = kinematics.get_point(frame, n1)
        p2 = kinematics.get_point(frame, n2)
        
        if p1 and p2:
            # Color logic directly from render.py
            c = "#8764B8" # Center (Purple)
            if "left" in n1 or "left" in n2: c = "#005FB8" # Left (Blue)
            elif "right" in n1 or "right" in n2: c = "#D83B01" # Right (Orange)

            fig.add_trace(go.Scatter(
                x=[p1[0], p2[0]], 
                y=[-p1[1], -p2[1]], # Y-Axis Inversion
                mode='lines', line=dict(color=c, width=4), hoverinfo='skip', showlegend=False
            ))

    # ── DRAW JOINTS ──
    xs, ys, names = [], [], []
    for name in VISIBLE_NAMES:
        p = kinematics.get_point(frame, name) 
        if p:
            xs.append(p[0])
            ys.append(-p[1])
            names.append(name.replace("_", " ").title())

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode='markers', marker=dict(size=6, color="#323130"),
        text=names, hoverinfo='text', showlegend=False
    ))

    # ── TRACKING LINE & CAMERA CENTERING ──
    hip = kinematics.get_point(frame, "hip_mid")
    center_x, center_y = 0.0, 0.0
    
    if hip:
        center_x, center_y = hip[0], -hip[1]
        # Draw the faint vertical reference line
        fig.add_vline(x=center_x, line_width=2, line_dash="dash", line_color="rgba(0,0,0,0.15)")

    # Lock Aspect Ratio to the runner's exact location
    fig.update_layout(
        xaxis=dict(title='X (Horizontal)', range=[center_x - 1.0, center_x + 1.0], scaleanchor="y", scaleratio=1),
        yaxis=dict(title='Y (Vertical)', range=[center_y - 1.2, center_y + 1.2]),
        height=600, margin=dict(l=0, r=0, b=0, t=0),
        plot_bgcolor='rgba(0,0,0,0.02)'
    )
    return fig

def render():
    col_back, col_title = st.columns([1, 10])
    with col_back:
        if st.button("⬅️ Back to Menu", width='stretch'):
            st.session_state.current_page = "launcher"
            st.rerun()
    with col_title:
        st.title("🦴 Precision Frame Inspector")

    with st.sidebar:
        st.title("Controls")
        st.subheader("DATA SOURCE")
        uploaded_file = st.file_uploader("Select Cleaned File (.parquet or .csv)", type=['parquet', 'csv'], key="viz_up")
        
        session = None
        if uploaded_file is not None:
            with st.spinner("Loading frames into memory..."):
                session = load_session_for_viz(uploaded_file.getvalue(), uploaded_file.name)
            
            st.success(f"Loaded {len(session.frames)} frames.")
            st.markdown("---")
            
            st.subheader("TIMELINE SCRUBBER")
            max_f = len(session.frames) - 1
            frame_idx = st.slider("Select Frame:", min_value=0, max_value=max_f, value=0, step=1)
            
            current_frame = session.frames[frame_idx]
            st.caption(f"⏱️ **Timestamp:** {current_frame.timestamp:.2f} seconds")

    if uploaded_file is not None and session is not None:
        col_skel, col_metrics = st.columns([2, 1], gap="large")
        
        with col_skel:
            with st.container(border=True):
                fig = draw_2d_skeleton(current_frame)
                st.plotly_chart(fig, use_container_width=True)

        with col_metrics:
            st.subheader("Frame Metrics")
            st.caption("Instantaneous joint angles for the selected frame.")
            
            vals = kinematics.compute_all_metrics(current_frame)
            
            with st.container(border=True):
                st.markdown("**Trunk Lean**")
                st.metric("Sagittal (Forward)", f"{vals['lean_x']:.1f}°")
                st.metric("Frontal (Side)", f"{vals['lean_z']:.1f}°")
            
            with st.container(border=True):
                st.markdown("**Knee Flexion**")
                st.metric("Left Knee", f"{vals['l_knee']:.1f}°")
                st.metric("Right Knee", f"{vals['r_knee']:.1f}°")

            with st.container(border=True):
                st.markdown("**Hip Flexion**")
                st.metric("Left Hip", f"{vals['l_hip']:.1f}°")
                st.metric("Right Hip", f"{vals['r_hip']:.1f}°")
    else:
        st.info("👈 Upload a dataset from the sidebar to inspect frames.")