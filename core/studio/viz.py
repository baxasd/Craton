import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io

from core.io import structs
from core.io.structs import BONES_LIST, VISIBLE_NAMES
from core.math import kinematics
from core.ui.theme import (
    COLOR_LEFT,
    COLOR_RIGHT,
    COLOR_CENTER,
    COLOR_JOINT,
    COLOR_SKELETON_BG,
    COLOR_REF_LINE,
    VIZ_BONE_WIDTH,
    VIZ_SPINE_WIDTH,
)


@st.cache_data(show_spinner=False)
def load_session_for_viz(file_bytes, filename):
    """Loads the file directly from RAM into a hierarchical Session object."""
    buffer = io.BytesIO(file_bytes)
    if filename.endswith(".parquet"):
        df = pd.read_parquet(buffer)
    else:
        df = pd.read_csv(buffer)
    return structs.df_to_session(df)


def draw_2d_skeleton(frame):
    """Hardware-accelerated 2D projection of the 3D skeleton."""
    fig = go.Figure()

    # ── DRAW BONES ──
    for n1, n2 in BONES_LIST:
        p1 = kinematics.get_point(frame, n1)
        p2 = kinematics.get_point(frame, n2)

        if p1 and p2:
            # UI THEME CONSTANTS APPLIED HERE
            c = COLOR_CENTER
            if "left" in n1 or "left" in n2:
                c = COLOR_LEFT
            elif "right" in n1 or "right" in n2:
                c = COLOR_RIGHT

            # Switch to thicker spine width if dealing with the trunk
            w = VIZ_SPINE_WIDTH if "mid" in n1 and "mid" in n2 else VIZ_BONE_WIDTH

            fig.add_trace(
                go.Scatter(
                    x=[p1[0], p2[0]],
                    y=[-p1[1], -p2[1]],  # Y-Axis Inversion
                    mode="lines",
                    line=dict(color=c, width=w),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    # ── DRAW JOINTS ──
    xs, ys, names = [], [], []
    for name in VISIBLE_NAMES:
        p = kinematics.get_point(frame, name)
        if p:
            xs.append(p[0])
            ys.append(-p[1])
            names.append(name.replace("_", " ").title())

    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            marker=dict(size=6, color=COLOR_JOINT),
            text=names,
            hoverinfo="text",
            showlegend=False,
        )
    )

    # ── TRACKING LINE & CAMERA CENTERING ──
    hip = kinematics.get_point(frame, "hip_mid")
    center_x, center_y = 0.0, 0.0

    if hip:
        center_x, center_y = hip[0], -hip[1]
        fig.add_vline(
            x=center_x, line_width=2, line_dash="dash", line_color=COLOR_REF_LINE
        )

    fig.update_layout(
        xaxis=dict(
            title="X (Horizontal)",
            range=[center_x - 1.0, center_x + 1.0],
            scaleanchor="y",
            scaleratio=1,
        ),
        yaxis=dict(title="Y (Vertical)", range=[center_y - 1.2, center_y + 1.2]),
        height=600,
        margin=dict(l=0, r=0, b=0, t=0),
        plot_bgcolor=COLOR_SKELETON_BG,
    )
    return fig


def render():

    st.title("Motion Lab")

    with st.sidebar:
        st.markdown("# Controls")
        uploaded_file = st.file_uploader(
            "Select File (.parquet or .csv)", type=["parquet", "csv"], key="viz_up"
        )

        session = None
        if uploaded_file is not None:
            with st.spinner("Loading frames into memory..."):
                session = load_session_for_viz(
                    uploaded_file.getvalue(), uploaded_file.name
                )

            st.success(f"Loaded {len(session.frames)} frames.")
            st.subheader("Frames")
            max_f = len(session.frames) - 1
            frame_idx = st.slider(
                "Select Frame:", min_value=0, max_value=max_f, value=0, step=1
            )

            current_frame = session.frames[frame_idx]
            st.caption(f"**Timestamp:** {current_frame.timestamp:.2f} seconds")

        st.markdown("---")
        if st.button("Back to Menu", width="stretch"):
            st.session_state.current_page = "hub"
            st.rerun()

    if uploaded_file is not None and session is not None:

        # ─── 1. METRICS SECTION (MOVED TO TOP) ───
        st.subheader("Frame Metrics")
        st.caption("Instantaneous joint angles for the selected frame.")

        vals = kinematics.compute_all_metrics(current_frame)

        metrics_config = [
            (
                "Trunk Lean",
                [("Sagittal (Forward)", "lean_x"), ("Frontal (Side)", "lean_z")],
            ),
            ("Knee Flexion", [("Left Knee", "l_knee"), ("Right Knee", "r_knee")]),
            ("Hip Flexion", [("Left Hip", "l_hip"), ("Right Hip", "r_hip")]),
        ]

        # Display the 3 metric cards side-by-side
        metric_cols = st.columns(3)
        for i, (section_title, metrics) in enumerate(metrics_config):
            with metric_cols[i]:
                with st.container(border=True):
                    st.markdown(f"**{section_title}**")

                    html_block = ""
                    for label, key in metrics:
                        val_str = f"{vals[key]:.1f}&deg;"
                        html_block += f"""
                        <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(128, 128, 128, 0.2);">
                            <span>{label}</span>
                            <strong>{val_str}</strong>
                        </div>
                        """
                    st.markdown(html_block, unsafe_allow_html=True)

        st.write("")  # Quick spacer

        # ─── 2. SKELETON SECTION (MOVED BELOW) ───
        st.subheader("Skeletal Projection")
        st.caption("2D tracking visualization.")

        with st.container(border=True):
            fig = draw_2d_skeleton(current_frame)
            st.plotly_chart(fig, width="stretch")

    else:
        st.info("Upload a dataset to generate motion preview.")
