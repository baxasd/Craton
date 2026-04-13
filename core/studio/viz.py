import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io

from core.io import structs
from core.io.structs import BONES_LIST, VISIBLE_NAMES
from core.math import kinematics
from core.ui.theme import COLOR_LEFT, COLOR_RIGHT, COLOR_CENTER, COLOR_JOINT, COLOR_SKELETON_BG, COLOR_REF_LINE, VIZ_BONE_WIDTH, VIZ_SPINE_WIDTH

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
    
    for (n1, n2) in BONES_LIST:
        p1 = kinematics.get_point(frame, n1)
        p2 = kinematics.get_point(frame, n2)
        
        if p1 and p2:
            c = COLOR_CENTER 
            if "left" in n1 or "left" in n2: c = COLOR_LEFT 
            elif "right" in n1 or "right" in n2: c = COLOR_RIGHT 
            
            w = VIZ_SPINE_WIDTH if "mid" in n1 and "mid" in n2 else VIZ_BONE_WIDTH

            fig.add_trace(go.Scatter(
                x=[p1[0], p2[0]], 
                y=[-p1[1], -p2[1]],
                mode='lines', line=dict(color=c, width=w), hoverinfo='skip', showlegend=False
            ))

    xs, ys, names = [], [], []
    for name in VISIBLE_NAMES:
        p = kinematics.get_point(frame, name) 
        if p:
            xs.append(p[0])
            ys.append(-p[1])
            names.append(name.replace("_", " ").title())

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode='markers', marker=dict(size=6, color=COLOR_JOINT),
        text=names, hoverinfo='text', showlegend=False
    ))

    # ── TRACKING LINE & CAMERA CENTERING ──
    hip = kinematics.get_point(frame, "hip_mid")
    center_x, center_y = 0.0, 0.0
    
    if hip:
        center_x, center_y = hip[0], -hip[1]
        fig.add_vline(x=center_x, line_width=2, line_dash="dash", line_color=COLOR_REF_LINE)

    fig.update_layout(
        xaxis=dict(title='X (Horizontal)', range=[center_x - 1.0, center_x + 1.0], scaleanchor="y", scaleratio=1),
        yaxis=dict(title='Y (Vertical)', range=[center_y - 1.2, center_y + 1.2]),
        height=600, margin=dict(l=0, r=0, b=0, t=0),
        plot_bgcolor=COLOR_SKELETON_BG
    )
    return fig

def render():
    
    st.write("")
    if st.button("← Back to Hub", type="tertiary"):
        st.session_state.current_page = "hub"
        st.rerun()
        
    st.markdown("<h2 style='margin-top: -15px;'>Motion Lab</h2>", unsafe_allow_html=True)

    if st.session_state.get('viz_bytes') is None:
        
        st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
        
        _, center_col, _ = st.columns([1, 2, 1])
        
        with center_col:
            with st.container(border=True):
                st.markdown("<h3 style='text-align: center;'>Import Motion Data</h3>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: #666;'>Upload cleaned motion data to visualize skeletal tracking.</p>", unsafe_allow_html=True)
                
                viz_file = st.file_uploader("Upload File (.parquet or .csv)", type=['parquet', 'csv'], label_visibility="collapsed")
                
                if viz_file is not None:
                    st.session_state.viz_bytes = viz_file.getvalue()
                    st.session_state.viz_filename = viz_file.name
                    st.rerun()

    else:
        file_bytes = st.session_state.viz_bytes
        filename = st.session_state.viz_filename
        
        with st.spinner("Loading frames into memory..."):
            session = load_session_for_viz(file_bytes, filename)
        
        st.success(f"Loaded {len(session.frames)} frames.")

        with st.sidebar:
            st.markdown("### Playback Controls")
            
            max_f = len(session.frames) - 1
            frame_idx = st.slider("Select Frame:", min_value=0, max_value=max_f, value=0, step=1)
            
            current_frame = session.frames[frame_idx]
            st.caption(f"**Timestamp:** {current_frame.timestamp:.2f} seconds")
            
            st.divider()
            
            if st.button("Clear Workspace", width='stretch'):
                st.session_state.viz_bytes = None
                st.session_state.viz_filename = None
                st.rerun()

        vals = kinematics.compute_all_metrics(current_frame)
        
        with st.container(border=True):
            st.markdown("#### Frame Metrics")
            metrics_dict = {
                "Trunk Lean (Sagittal)": f"{vals['lean_x']:.1f}°",
                "Trunk Lean (Frontal)": f"{vals['lean_z']:.1f}°",
                "Left Knee Flexion": f"{vals['l_knee']:.1f}°",
                "Right Knee Flexion": f"{vals['r_knee']:.1f}°",
                "Left Hip Flexion": f"{vals['l_hip']:.1f}°",
                "Right Hip Flexion": f"{vals['r_hip']:.1f}°"
            }
            
            st.dataframe(pd.DataFrame([metrics_dict]), hide_index=True, width='stretch')

        with st.container(border=True):
            st.markdown("##### 2D Projection")
            fig = draw_2d_skeleton(current_frame)
            
            st.plotly_chart(fig, width='stretch')