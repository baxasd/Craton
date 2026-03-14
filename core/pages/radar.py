import streamlit as st
import numpy as np
import plotly.graph_objects as go
import tempfile
import os
import configparser

from core.radar.parser import RadarConfig
from core.radar.dsp import RecordingSession, extract_gait_metrics
from core.ui.theme import COLOR_RADAR_BG, COLOR_CENTROID_MAIN, COLOR_CENTROID_SHADOW, COLOR_ZERO_LINE

# ─── CACHED FFT DSP ENGINE ───────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def process_radar_data(file_bytes, range_lo, range_hi, smooth_window):
    """
    Saves the uploaded RAM buffer to a temp file, runs the heavy Texas Instruments 
    parser and FFT math, and returns the raw arrays.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix='.parquet') as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        cfg_ini = configparser.ConfigParser()
        cfg_ini.read('settings.ini')
        hw_cfg_file = cfg_ini.get('Hardware', 'radar_cfg_file', fallback='settings.json')
        
        try:
            radar_cfg = RadarConfig(hw_cfg_file)
        except:
            radar_cfg = None

        session = RecordingSession(tmp_path, radar_cfg)
        spec, t_axis, v_axis, centroid = session.build_spectrogram(range_lo, range_hi, smooth_window)
        peak_v, mean_abs, spm = extract_gait_metrics(spec, t_axis, v_axis)
        
        fps = session.num_frames / session.duration_s if session.duration_s > 0 else 0
        res = radar_cfg.dopRes if radar_cfg else 0.0

        return spec, t_axis, v_axis, centroid, peak_v, mean_abs, spm, session.duration_s, session.num_frames, fps, res
        
    finally:
        os.remove(tmp_path)


def render():
    col_back, col_title = st.columns([1, 10])
    with col_back:
        if st.button("⬅️ Back to Menu", width='stretch'):
            st.session_state.current_page = "hub"
            st.rerun()
    with col_title:
        st.title("📡 Radar Spectrogram Analysis")

    with st.sidebar:
        st.title("Radar Controls")
        
        st.subheader("DATA SOURCE")
        uploaded_file = st.file_uploader("Select Parquet File", type=['parquet'], key="radar_up")
        
        st.markdown("---")
        st.subheader("RANGE GATE (Meters)")
        col_lo, col_hi = st.columns(2)
        range_lo = col_lo.number_input("Min Range", min_value=0.0, max_value=49.0, value=0.0, step=0.1)
        range_hi = col_hi.number_input("Max Range", min_value=0.1, max_value=50.0, value=5.0, step=0.1)
        
        st.markdown("---")
        st.subheader("VISUALS")
        
        cmap_mapping = {'jet': 'Jet', 'inferno': 'Inferno', 'turbo': 'Turbo', 'viridis': 'Viridis', 'plasma': 'Plasma'}
        cmap_sel = st.selectbox("Theme:", list(cmap_mapping.keys()), index=0)
        plotly_cmap = cmap_mapping[cmap_sel]
        
        cont_lo, cont_hi = st.slider("Contrast Percentiles:", min_value=0.0, max_value=100.0, value=(40.0, 99.5), step=0.5)
        smooth_win = st.number_input("Smoothing Window:", min_value=1, max_value=10, value=3, step=1)
        show_centroid = st.checkbox("Overlay Cadence Line", value=True)

    if uploaded_file is not None:
        with st.spinner("Crunching Micro-Doppler FFTs..."):
            spec, t_axis, v_axis, centroid, peak_v, mean_abs, spm, dur, frames, fps, res = process_radar_data(
                uploaded_file.getvalue(), range_lo, range_hi, int(smooth_win)
            )

        st.subheader("Gait Statistics")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Estimated Cadence", f"{spm:.0f} SPM" if spm > 0 else "--")
        c2.metric("Peak Velocity", f"{peak_v:+.2f} m/s")
        c3.metric("Mean |Vel|", f"{mean_abs:.2f} m/s")
        c4.metric("Session", f"{dur:.1f}s ({frames} frames)")
        
        st.markdown("---")
        st.subheader("Micro-Doppler Spectrogram")
        
        sub_spec = spec[::4, ::4]
        z_min = float(np.percentile(sub_spec, cont_lo))
        z_max = float(np.percentile(sub_spec, cont_hi))
        if z_min >= z_max: z_max = z_min + 0.1
        
        fig = go.Figure()
        
        fig.add_trace(go.Heatmap(
            z=spec.T, x=t_axis, y=v_axis,
            colorscale=plotly_cmap,
            zmin=z_min, zmax=z_max,
            hoverinfo='skip', 
            showscale=False   
        ))

        # UI THEME CONSTANTS APPLIED HERE
        if show_centroid and centroid is not None:
            fig.add_trace(go.Scatter(x=t_axis, y=centroid, mode='lines', line=dict(color=COLOR_CENTROID_SHADOW, width=4), hoverinfo='skip', showlegend=False))
            fig.add_trace(go.Scatter(x=t_axis, y=centroid, mode='lines', name='Mass Centroid', line=dict(color=COLOR_CENTROID_MAIN, width=1.5)))

        fig.add_hline(y=0, line_dash="dash", line_color=COLOR_ZERO_LINE, line_width=1)

        fig.update_layout(
            xaxis_title="Time (Seconds)",
            yaxis_title="Doppler Velocity (m/s)",
            height=600,
            margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor=COLOR_RADAR_BG,
            paper_bgcolor='rgba(0,0,0,0)'
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("👈 Upload a raw mmWave Parquet file from the left sidebar to generate the spectrogram.")