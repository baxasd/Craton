import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import tempfile
import os
import configparser
from scipy.signal import find_peaks, butter, filtfilt, welch
from scipy.ndimage import uniform_filter1d
from src.radar.parse import RadarConfig
from src.radar.dsp import RecordingSession
from src.utils.theme import (
    COLOR_RADAR_BG, COLOR_CENTROID_MAIN, COLOR_CENTROID_SHADOW,
    COLOR_ZERO_LINE, SETTINGS_PATH, COLOR_LEFT, COLOR_RIGHT,
)

# =====================================================================
# VERSION TAG — increment this to bust Streamlit's cache automatically
# when the analysis logic changes between deployments.
# =====================================================================
_ANALYSIS_VERSION = "v5"


# =====================================================================
# CORE ANALYSIS LOGIC
# =====================================================================

def analyze_gait_performance(time, velocity, cfg):
    """
    Analyze radar micro-Doppler centroid velocity for a treadmill runner.

    Parameters
    ----------
    time     : np.ndarray  — time axis in seconds
    velocity : np.ndarray  — raw Doppler centroid (radar units)
    cfg      : dict        — all tunable parameters from the UI sidebar

    Signal model
    ------------
    The Doppler centroid from a rear-facing radar pointed at a treadmill
    has two overlapping contributions:

      1. Treadmill belt  — continuous negative Doppler (belt surface moves
                           away from radar). Creates a negative DC offset.
      2. Runner's legs   — periodic positive Doppler swings as each foot
                           pushes off toward the radar.

    The result is a signal with a non-zero DC level (positive or negative
    depending on which return dominates) with the step rhythm sitting in
    the AC band on top. We must separate these before doing any detection.

    Strategy
    --------
    - Apply bandpass (hp_cutoff → lp_cutoff Hz) to isolate gait oscillation.
    - Run find_peaks on this zero-mean AC component.
    - Run Welch PSD on the AC component to find stride frequency.
    - Use raw smoothed signal only for spectrogram overlay display.
    """
    v_raw = velocity * cfg["velocity_scale"]
    dt    = float(np.mean(np.diff(time))) if len(time) > 1 else 0.1
    fs    = 1.0 / dt

    # ------------------------------------------------------------------
    # 1. Display signal — light low-pass only, keeps DC for overlay
    # ------------------------------------------------------------------
    try:
        bl, al = butter(4, min(cfg["lp_cutoff"] / (fs / 2), 0.99), btype='low')
        v_display = filtfilt(bl, al, v_raw)
    except Exception:
        v_display = v_raw.copy()

    # ------------------------------------------------------------------
    # 2. AC component — bandpass to isolate gait oscillation
    #    High-pass removes: DC offset, treadmill belt Doppler, slow drift
    #    Low-pass removes:  frame-to-frame radar noise
    # ------------------------------------------------------------------
    try:
        bh, ah = butter(2, max(cfg["hp_cutoff"] / (fs / 2), 1e-4), btype='high')
        v_ac = filtfilt(bh, ah, v_raw)
    except Exception:
        v_ac = v_raw - np.mean(v_raw)

    try:
        bl2, al2 = butter(4, min(cfg["lp_cutoff"] / (fs / 2), 0.99), btype='low')
        v_ac = filtfilt(bl2, al2, v_ac)
    except Exception:
        pass

    # ------------------------------------------------------------------
    # 3. Spectral cadence (on AC component)
    #    Centroid oscillates at STRIDE rate = half step rate.
    #    Search stride band, multiply by 2 for step SPM.
    # ------------------------------------------------------------------
    try:
        nperseg       = min(len(v_ac), int(fs * 8))
        f_psd, pxx    = welch(v_ac, fs, nperseg=nperseg)
        stride_lo     = cfg["step_freq_min_hz"] / 2
        stride_hi     = cfg["step_freq_max_hz"] / 2
        stride_idx    = (f_psd >= stride_lo) & (f_psd <= stride_hi)
        dom_stride_hz = f_psd[stride_idx][np.argmax(pxx[stride_idx])] if np.any(stride_idx) else 1.25
    except Exception:
        dom_stride_hz = 1.25

    freq_spm     = dom_stride_hz * 2 * 60
    expected_gap = 1.0 / (dom_stride_hz * 2)   # seconds per step

    # ------------------------------------------------------------------
    # 4. Time-domain step detection (on AC component)
    # ------------------------------------------------------------------
    min_dist   = max(1, int(fs * cfg["min_step_gap_s"]))
    ac_std     = float(np.std(v_ac))
    prominence = max(ac_std * cfg["prominence_factor"], 1e-5)

    peaks, _ = find_peaks(v_ac, distance=min_dist, prominence=prominence)

    n_steps  = len(peaks)
    duration = float(time[-1] - time[0]) if len(time) > 1 else 1.0
    time_spm = (n_steps / duration * 60) if duration > 0 else 0.0

    # ------------------------------------------------------------------
    # 5. Confidence — exponential decay of SPM divergence
    # ------------------------------------------------------------------
    divergence = abs(freq_spm - time_spm) / freq_spm if freq_spm > 0 else 1.0
    confidence = float(np.clip(100.0 * np.exp(-3.0 * divergence), 0, 100))

    # ------------------------------------------------------------------
    # 6. Displacement proxy — integrate AC, then remove integration drift
    # ------------------------------------------------------------------
    displacement = np.cumsum(v_ac * dt)
    try:
        bd, ad      = butter(2, max(0.02 / (fs / 2), 1e-4), btype='high')
        displacement = filtfilt(bd, ad, displacement)
    except Exception:
        displacement = displacement - np.mean(displacement)

    # ------------------------------------------------------------------
    # 7. Drift / correction event detection (on smoothed displacement)
    # ------------------------------------------------------------------
    window_size   = max(1, int(fs * 2.0)) 
    smoothed_disp = uniform_filter1d(displacement, size=window_size)
    disp_sd       = float(np.std(displacement))
    drift_limit   = cfg["drift_thresh_factor"] * disp_sd

    drifts        = smoothed_disp < -drift_limit
    corrections   = smoothed_disp >  drift_limit

    # ------------------------------------------------------------------
    # 8. Phase asymmetry tracker
    # ------------------------------------------------------------------
    set_a, set_b = [], []
    current      = 0

    for i, pk in enumerate(peaks):
        if i == 0:
            set_a.append(pk)
        else:
            gap         = time[pk] - time[peaks[i - 1]]
            steps_taken = max(1, round(gap / expected_gap))
            if steps_taken % 2 == 1:
                current ^= 1
            (set_a if current == 0 else set_b).append(pk)

    set_a = np.array(set_a, dtype=int)
    set_b = np.array(set_b, dtype=int)

    amp_asym = 0.0
    if len(set_a) > 0 and len(set_b) > 0:
        ma    = np.mean(v_ac[set_a])
        mb    = np.mean(v_ac[set_b])
        denom = (abs(ma) + abs(mb)) / 2
        if denom > 0:
            amp_asym = abs(ma - mb) / denom * 100

    set_a_lut = set(set_a.tolist())
    set_b_lut = set(set_b.tolist())
    gaps_ab, gaps_ba = [], []
    for i in range(len(peaks) - 1):
        p1, p2 = int(peaks[i]), int(peaks[i + 1])
        g      = time[p2] - time[p1]
        if p1 in set_a_lut and p2 in set_b_lut:
            gaps_ab.append(g)
        elif p1 in set_b_lut and p2 in set_a_lut:
            gaps_ba.append(g)

    temp_asym = 0.0
    if gaps_ab and gaps_ba:
        temp_asym = abs(np.mean(gaps_ab) - np.mean(gaps_ba))

    return {
        # signals
        "time":                  time,
        "v_raw":                 v_raw,
        "v_display":             v_display,
        "v_ac":                  v_ac,
        "displacement":          displacement,
        "smoothed_disp":         smoothed_disp,
        # detection
        "peaks":                 peaks,
        "step_set_a":            set_a,
        "step_set_b":            set_b,
        "drifts":                drifts,
        "corrections":           corrections,
        "disp_sd":               disp_sd,
        "drift_limit":           drift_limit,
        # metrics
        "total_step_count":      n_steps,
        "time_spm":              time_spm,
        "freq_spm":              freq_spm,
        "confidence":            confidence,
        "amp_asymmetry":         amp_asym,
        "temp_asymmetry":        temp_asym,
        # version tag — ensures cache never serves stale keys
        "_version":              _ANALYSIS_VERSION,
    }


# =====================================================================
# PLOTTING
# =====================================================================

def create_gait_plotly_figures(r):
    """Three gait analysis plots. All detection uses v_ac (AC component)."""

    time = r["time"]
    v_ac = r["v_ac"]
    disp = r["displacement"]
    peaks = r["peaks"]
    idx_a = r["step_set_a"]
    idx_b = r["step_set_b"]

    _layout = dict(height=300, margin=dict(l=0, r=0, t=40, b=0))

    # ------------------------------------------------------------------
    # Figure 1 — Gait Oscillation & Step Detection
    # ------------------------------------------------------------------
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=time, y=v_ac,
        name="Gait oscillation (AC)",
        line=dict(color="#4A90D9", width=1.2),
    ))
    if len(peaks):
        fig1.add_trace(go.Scatter(
            x=time[peaks], y=v_ac[peaks],
            mode='markers', name="Detected Steps",
            marker=dict(color="red", size=7),
        ))
    fig1.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig1.update_layout(
        title=f"Gait Oscillation & Step Detection — {r['total_step_count']} steps detected",
        xaxis_title="Time (s)", yaxis_title="AC Velocity (m/s)",
        **_layout,
    )

    # ------------------------------------------------------------------
    # Figure 2 — Positional Drift Proxy
    # ------------------------------------------------------------------
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=time, y=disp,
        name="Raw Displacement",
        line=dict(color="blue", width=1),
        opacity=0.3
    ))
    fig2.add_trace(go.Scatter(
        x=time, y=r["smoothed_disp"],
        name="Drift Trend",
        line=dict(color="orange", width=3),
    ))
    
    limit = r["drift_limit"]
    fig2.add_hline(y=limit, line_dash="dot", line_color="green", annotation_text="+SD (Correction Limit)")
    fig2.add_hline(y=-limit, line_dash="dot", line_color="red", annotation_text="-SD (Drift Limit)")
    fig2.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
    fig2.update_layout(
        title="Motion Centroid Positional Drift (relative proxy)",
        xaxis_title="Time (s)", yaxis_title="Relative Position (m)",
        **_layout,
    )

    # ------------------------------------------------------------------
    # Figure 3 — Phase Asymmetry
    # ------------------------------------------------------------------
    fig3 = go.Figure()
    if len(idx_a):
        fig3.add_trace(go.Bar(
            x=time[idx_a], y=v_ac[idx_a],
            name="Phase A (e.g. Left)",
            marker_color=COLOR_LEFT, width=0.5,
        ))
    if len(idx_b):
        fig3.add_trace(go.Bar(
            x=time[idx_b], y=v_ac[idx_b],
            name="Phase B (e.g. Right)",
            marker_color=COLOR_RIGHT, width=0.5,
        ))
    fig3.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.4)
    fig3.update_layout(
        title=f"Step Phase Amplitudes — Asymmetry: {r['amp_asymmetry']:.1f}%  |  Temporal: {r['temp_asymmetry']:.3f} s",
        xaxis_title="Time (s)", yaxis_title="AC Peak Velocity (m/s)",
        barmode='overlay',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        **_layout,
    )

    return fig1, fig2, fig3


# =====================================================================
# CACHED DATA LOADER
# =====================================================================

@st.cache_data(show_spinner=False)
def process_radar_data(file_bytes, range_lo, range_hi, smooth_window, cfg_tuple):
    """
    cfg_tuple contains all analysis parameters as a hashable tuple so
    Streamlit re-runs the analysis whenever any parameter changes.
    """
    cfg = dict(cfg_tuple)   # convert back to dict for use in analysis

    with tempfile.NamedTemporaryFile(delete=False, suffix='.parquet') as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        config      = configparser.ConfigParser(interpolation=None)
        config.read(SETTINGS_PATH)
        hw_cfg_file = config.get('Hardware', 'radar_cfg_file')
        try:
            radar_cfg = RadarConfig(hw_cfg_file)
        except Exception:
            radar_cfg = None

        session              = RecordingSession(tmp_path, radar_cfg)
        spec, t_axis, v_axis, centroid = session.build_spectrogram(range_lo, range_hi, smooth_window)
        gait_results         = analyze_gait_performance(t_axis, centroid, cfg)
        fps                  = session.num_frames / session.duration_s if session.duration_s > 0 else 0.0
        dop_res              = radar_cfg.dopRes if radar_cfg else 0.0

        return spec, t_axis, v_axis, centroid, gait_results, session.duration_s, session.num_frames, fps, dop_res
    finally:
        os.remove(tmp_path)


# =====================================================================
# VIEW RENDERER
# =====================================================================

def render():
    st.write("")
    if st.button("← Back to Hub", type="tertiary"):
        st.session_state.current_page = "hub"
        st.rerun()
    st.markdown("<h2 style='margin-top: -15px;'>Radar Analysis</h2>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Upload screen
    # ------------------------------------------------------------------
    if st.session_state.get('radar_bytes') is None:
        st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
        _, center_col, _ = st.columns([1, 2, 1])
        with center_col:
            with st.container(border=True):
                st.markdown("<h3 style='text-align: center;'>Import Radar Session</h3>", unsafe_allow_html=True)
                radar_file = st.file_uploader("Upload File", type=['parquet'], label_visibility="collapsed")
                if radar_file is not None:
                    st.session_state.radar_bytes = radar_file.getvalue()
                    st.rerun()
        return

    # ------------------------------------------------------------------
    # Sidebar — all tunable parameters exposed
    # ------------------------------------------------------------------
    with st.sidebar:

        st.markdown("### Range Filter")
        col_lo, col_hi = st.columns(2)
        range_lo = col_lo.number_input("Min (m)", min_value=0.0,  max_value=49.0, value=0.0, step=0.1)
        range_hi = col_hi.number_input("Max (m)", min_value=0.1,  max_value=50.0, value=5.0, step=0.1)

        st.markdown("### Calibration")
        velocity_scale = st.number_input(
            "Velocity Scale Factor",
            min_value=0.001, max_value=1.0,
            value=round(2.0 / 15.0, 4), step=0.001, format="%.4f",
            help="Converts raw radar Doppler units to m/s.",
        )

        st.markdown("### Signal Filtering")
        st.caption(
            "The centroid has a DC offset from the treadmill belt. "
            "The high-pass removes that; the low-pass removes frame noise."
        )
        hp_cutoff = st.slider(
            "High-pass cutoff (Hz)",
            min_value=0.1, max_value=1.5, value=0.5, step=0.05,
            help="Removes DC offset + treadmill belt Doppler. "
                 "Raise if the signal still has a flat baseline after filtering.",
        )
        lp_cutoff = st.slider(
            "Low-pass cutoff (Hz)",
            min_value=2.0, max_value=10.0, value=3.5, step=0.5,
            help="Removes high-frequency radar noise. "
                 "Lower if you see too much jitter in the AC signal.",
        )

        st.markdown("### Step Detection")
        step_freq_min = st.slider(
            "Min step freq (Hz)",
            min_value=0.5, max_value=2.5, value=2.2, step=0.1,
            help="90 SPM = 1.5 Hz. Lower only for very slow walking.",
        )
        step_freq_max = st.slider(
            "Max step freq (Hz)",
            min_value=2.0, max_value=6.0, value=3.5, step=0.1,
            help="240 SPM = 4.0 Hz. Upper physiological limit for sprinting.",
        )
        min_step_gap = st.slider(
            "Min step gap (s)",
            min_value=0.15, max_value=0.5, value=0.28, step=0.01,
            help="Minimum time between two steps. 0.25 s = 4 Hz physiological limit.",
        )
        prominence_factor = st.slider(
            "Peak prominence factor",
            min_value=0.05, max_value=1.0, value=0.45, step=0.05,
            help="Fraction of signal std required for a peak to count as a step. "
                 "Raise if false positives, lower if real steps are missed.",
        )

        st.markdown("### Drift Detection")
        drift_thresh_factor = st.slider(
            "Drift threshold factor",
            min_value=0.5, max_value=5.0, value=1.0, step=0.1,
            help="Multiplier on standard deviation for drift/correction events.",
        )

        st.markdown("### Visual Overlays")
        cmap_sel    = st.selectbox("Colormap:", ['Jet', 'Inferno', 'Plasma'], index=0)
        cont_lo, cont_hi = st.slider(
            "Contrast Percentiles:", min_value=0.0, max_value=100.0, value=(40.0, 99.5), step=0.5,
        )
        smooth_win  = st.number_input("DSP Smoothing Window:", min_value=1, max_value=10, value=3, step=1)
        show_centroid = st.checkbox("Overlay Centroid Line", value=True)

        st.divider()
        if st.button("Clear Workspace", use_container_width=True):
            st.session_state.radar_bytes = None
            st.rerun()

    # Bundle all analysis params into a sorted tuple for cache keying
    cfg_tuple = tuple(sorted({
        "velocity_scale":      velocity_scale,
        "hp_cutoff":           hp_cutoff,
        "lp_cutoff":           lp_cutoff,
        "step_freq_min_hz":    step_freq_min,
        "step_freq_max_hz":    step_freq_max,
        "min_step_gap_s":      min_step_gap,
        "prominence_factor":   prominence_factor,
        "drift_thresh_factor": drift_thresh_factor,
        "_version":            _ANALYSIS_VERSION,  # forces cache bust on code changes
    }.items()))

    # ------------------------------------------------------------------
    # Process
    # ------------------------------------------------------------------
    with st.spinner("Crunching Micro-Doppler FFTs..."):
        spec, t_axis, v_axis, centroid, gait, dur, frames, fps, dop_res = process_radar_data(
            st.session_state.radar_bytes,
            range_lo, range_hi, int(smooth_win),
            cfg_tuple,
        )

    # ------------------------------------------------------------------
    # Metrics summary
    # ------------------------------------------------------------------
    with st.container(border=True):
        st.markdown("**Gait Performance Metrics**")
        stats = {
            "Steps":         f"{gait['total_step_count']}",
            "Time SPM":      f"{gait['time_spm']:.1f}",
            "Spectral SPM":  f"{gait['freq_spm']:.1f}",
            "Confidence":    f"{gait['confidence']:.1f}%",
            "Amp Asym (%)":  f"{gait['amp_asymmetry']:.1f}%",
            "Temp Asym (s)": f"{gait['temp_asymmetry']:.3f}",
        }
        st.dataframe(pd.DataFrame([stats]), hide_index=True, use_container_width=True)

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    tab1, tab2 = st.tabs(["Micro-Doppler Spectrogram", "Gait Analysis Dashboard"])

    with tab1:
        with st.container(border=True):
            sub_spec = spec[::4, ::4]
            z_min    = float(np.percentile(sub_spec, cont_lo))
            z_max    = float(np.percentile(sub_spec, cont_hi))
            if z_min >= z_max:
                z_max = z_min + 0.1

            fig = go.Figure()
            fig.add_trace(go.Heatmap(
                z=spec.T, x=t_axis, y=v_axis,
                colorscale=cmap_sel,
                zmin=z_min, zmax=z_max,
                hoverinfo='skip', showscale=False,
            ))
            if show_centroid and centroid is not None:
                fig.add_trace(go.Scatter(
                    x=t_axis, y=centroid, mode='lines',
                    line=dict(color=COLOR_CENTROID_SHADOW, width=4),
                    hoverinfo='skip', showlegend=False,
                ))
                fig.add_trace(go.Scatter(
                    x=t_axis, y=centroid, mode='lines',
                    name='Motion Centroid',
                    line=dict(color=COLOR_CENTROID_MAIN, width=1.5),
                    showlegend=False,
                ))
            fig.add_hline(y=0, line_dash="dash", line_color=COLOR_ZERO_LINE, line_width=1)
            fig.update_layout(
                xaxis_title="Time (s)", yaxis_title="Velocity (m/s)",
                height=500, margin=dict(l=0, r=0, t=20, b=0),
                plot_bgcolor=COLOR_RADAR_BG, paper_bgcolor='rgba(0,0,0,0)',
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.info(
            "💡 **Signal model:** The Doppler centroid contains a DC offset from the treadmill belt "
            "(belt surface moves away from the radar, creating a persistent negative Doppler). "
            "The high-pass filter removes this so step rhythm can be detected in the AC oscillation. "
            "Phase A/B are oscillatory proxies — single-point radar cannot identify true left/right limbs. "
            "Displacement is a relative proxy, not absolute position."
        )
        f1, f2, f3 = create_gait_plotly_figures(gait)
        st.plotly_chart(f1, use_container_width=True)
        st.plotly_chart(f2, use_container_width=True)
        st.plotly_chart(f3, use_container_width=True)