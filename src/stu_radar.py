import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import tempfile
import os
import configparser
from rad_parse import RadarConfig
from rad_dsp import RecordingSession, extract_gait_metrics
from ui_theme import COLOR_RADAR_BG, COLOR_CENTROID_MAIN, COLOR_CENTROID_SHADOW, COLOR_ZERO_LINE, SETTINGS_PATH

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
        config = configparser.ConfigParser(interpolation=None)
        config.read(SETTINGS_PATH)
        hw_cfg_file = config.get('Hardware', 'radar_cfg_file')
        
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
    
    st.write("")
    if st.button("← Back to Hub", type="tertiary"):
        st.session_state.current_page = "hub"
        st.rerun()
        
    st.markdown("<h2 style='margin-top: -15px;'>Radar Analysis</h2>", unsafe_allow_html=True)

    if st.session_state.get('radar_bytes') is None:
    
        st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
        
        _, center_col, _ = st.columns([1, 2, 1])
        
        with center_col:
            with st.container(border=True):
                st.markdown("<h3 style='text-align: center;'>Import Radar Session</h3>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: #666;'>Upload raw mmWave telemetry to generate the Micro-Doppler spectrogram.</p>", unsafe_allow_html=True)
                
                radar_file = st.file_uploader("Upload File", type=['parquet'], label_visibility="collapsed")
                
                if radar_file is not None:
                    st.session_state.radar_bytes = radar_file.getvalue()
                    st.rerun()

    else:
        file_bytes = st.session_state.radar_bytes

        with st.sidebar:
            st.markdown("### Range Filter")
            col_lo, col_hi = st.columns(2)
            range_lo = col_lo.number_input("Min Range", min_value=0.0, max_value=49.0, value=0.0, step=0.1)
            range_hi = col_hi.number_input("Max Range", min_value=0.1, max_value=50.0, value=5.0, step=0.1)
            
            st.markdown("### Visual Overlays")
            cmap_mapping = {'Jet': 'Jet', 'Inferno': 'Inferno', 'Plasma': 'Plasma'}
            cmap_sel = st.selectbox("Colormap:", list(cmap_mapping.keys()), index=0)
            plotly_cmap = cmap_mapping[cmap_sel]
            
            cont_lo, cont_hi = st.slider("Contrast Percentiles:", min_value=0.0, max_value=100.0, value=(40.0, 99.5), step=0.5)
            smooth_win = st.number_input("DSP Smoothing Window:", min_value=1, max_value=10, value=3, step=1)
            show_centroid = st.checkbox("Overlay Cadence Line", value=True)
            
            st.divider()

            if st.button("Clear Workspace", use_container_width=True):
                st.session_state.radar_bytes = None
                st.rerun()

        with st.spinner("Crunching Micro-Doppler FFTs..."):
            spec, t_axis, v_axis, centroid, peak_v, mean_abs, spm, dur, frames, fps, res = process_radar_data(
                file_bytes, range_lo, range_hi, int(smooth_win)
            )

        with st.container(border=True):
            st.markdown("Session Statistics")
            cadence_str = f"{spm:.0f}" if spm > 0 else "--"
            
            stats_dict = {
                "Cadence (SPM)": cadence_str,
                "Peak Vel (m/s)": f"{peak_v:+.2f}",
                "Mean |Vel| (m/s)": f"{mean_abs:.2f}",
                "Duration (s)": f"{dur:.1f}",
                "FPS": f"{fps:.1f}",
                "Frames": f"{int(frames)}"
            }
            
            st.dataframe(pd.DataFrame([stats_dict]), hide_index=True, width='stretch')

        with st.container(border=True):
            st.markdown("##### Micro-Doppler Spectrogram")
            
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

            if show_centroid and centroid is not None:
                fig.add_trace(go.Scatter(x=t_axis, y=centroid, mode='lines', line=dict(color=COLOR_CENTROID_SHADOW, width=4), hoverinfo='skip', showlegend=False))
                fig.add_trace(go.Scatter(x=t_axis, y=centroid, mode='lines', name='Mass Centroid', line=dict(color=COLOR_CENTROID_MAIN, width=1.5),  showlegend=False))

            fig.add_hline(y=0, line_dash="dash", line_color=COLOR_ZERO_LINE, line_width=1)

            fig.update_layout(
                xaxis_title="Time (Seconds)",
                yaxis_title="Doppler Velocity (m/s)",
                height=600,
                margin=dict(l=0, r=0, t=20, b=0),
                plot_bgcolor=COLOR_RADAR_BG,
                paper_bgcolor='rgba(0,0,0,0)'
            )

            st.plotly_chart(fig, width='stretch')