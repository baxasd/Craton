import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from src.data import types as structs
from src.maths import motion as kinematics
from src.maths.filter import PipelineProcessor
from src.utils.theme import COLOR_LEFT, COLOR_RIGHT, COLOR_CENTER, COLOR_RAW_DATA, COLOR_CLEAN_DATA, PREP_RAW_WIDTH, PREP_CLEAN_WIDTH

# =====================================================================
# DATA PROCESSING & PHYSICS PIPELINE
# =====================================================================

@st.cache_data(show_spinner=False)
def process_analysis_data(df_raw):
    """
    Core Mathematical Pipeline:
    1. Converts Pandas dataframe to Frame/Joint structures.
    2. Computes the physics (ROM, Angles, Drift).
    3. Aggregates data by second and minute.
    """
    session = structs.df_to_session(df_raw)
    ts_df, session_stats = kinematics.generate_analysis_report(session)
    
    ts_df['time_sec'] = np.floor(ts_df['timestamp']).astype(int)
    numeric_cols = [c for c in ts_df.columns if c not in ['frame', 'time_sec', 'timestamp']]
    
    df_per_sec = ts_df.groupby('time_sec')[numeric_cols].mean().reset_index()
    df_per_sec['timestamp'] = df_per_sec['time_sec']
    
    ts_df['time_min'] = np.floor(ts_df['timestamp'] / 60.0).astype(int)
    df_per_min = ts_df.groupby('time_min')[numeric_cols].mean().reset_index()
    df_per_min['timestamp'] = df_per_min['time_min']
    
    trend_metrics = {}
    if len(df_per_sec) > 1:
        x_mins = df_per_sec['time_sec'] / 60.0
        for col in numeric_cols:
            mask = ~np.isnan(df_per_sec[col])
            if mask.sum() > 1:
                slope, _ = np.polyfit(x_mins[mask], df_per_sec[col][mask], 1)
                trend_metrics[f"slope_{col}"] = slope

    stats_df = df_per_sec.drop(columns=['time_sec', 'timestamp', 'time_min'], errors='ignore').describe().T
    stats_df['trend/min'] = stats_df.index.map(lambda x: trend_metrics.get(f"slope_{x}", 0.0))

    for col in session_stats.columns:
        if col not in stats_df.index:
            stats_df.loc[col, 'mean'] = session_stats.loc['mean', col]

    return ts_df, df_per_sec, df_per_min, stats_df

# =====================================================================
# PLOTTING ENGINE
# =====================================================================

def create_kinematic_plot(df, x_col, y_cols, names, colors, title, show_env=False, show_trend=False, env_win=5, yaxis_title="Degrees (°)"):
    """
    Standardized Plotly rendering engine. 
    Gracefully handles missing columns to prevent application crashes.
    """
    fig = go.Figure()
    window_size = env_win if show_env else 1

    for y_col, name, color in zip(y_cols, names, colors):
        if y_col not in df.columns: continue
        
        y_vals = df[y_col].values
        x_vals = df[x_col].values
        
        if show_env:
            roll_mean = df[y_col].rolling(window_size, min_periods=1).mean().values
            roll_std = df[y_col].rolling(window_size, min_periods=1).std().fillna(0).values
            upper = roll_mean + roll_std
            lower = roll_mean - roll_std
            
            fig.add_trace(go.Scatter(x=x_vals, y=upper, mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=x_vals, y=lower, mode='lines', line=dict(width=0), fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (0.2,)}", fill='tonexty', showlegend=False, hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=x_vals, y=roll_mean, mode='lines', name=name, line=dict(color=color, width=2.5)))
        else:
            fig.add_trace(go.Scatter(x=x_vals, y=y_vals, mode='lines', name=name, line=dict(color=color, width=2.5)))

        if show_trend:
            mask = ~np.isnan(y_vals) & ~np.isnan(x_vals)
            if mask.sum() > 1:
                slope, intercept = np.polyfit(x_vals[mask], y_vals[mask], 1)
                trend_y = slope * x_vals + intercept
                fig.add_trace(go.Scatter(x=x_vals, y=trend_y, mode='lines', name=f"{name} Trend", line=dict(color=color, width=1.5, dash='dash'), hoverinfo='skip'))

    fig.update_layout(
        title=title, xaxis_title=x_col.capitalize(), yaxis_title=yaxis_title,
        hovermode="x unified", margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

# =====================================================================
# VIEW: DATA PREPARATION
# =====================================================================

def render_preparation():
    """Renders the Data Import and DSP pipeline UI."""
    st.write('')
    if st.button("← Back to Hub", type='tertiary'):
        st.session_state.current_page = "hub"
        st.rerun()
        
    st.markdown("<h2 style='margin-top: -15px;'>Data Preparation</h2>", unsafe_allow_html=True)
    
    if st.session_state.get('raw_df') is None:
        st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
        _, col2, _ = st.columns([1,2,1])
        
        with col2:
            with st.container(border=True):
                st.markdown("<h3 style='text-align: center;'>Import Raw Dataset</h3>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: #666;'>Upload raw tracking data to run the DSP cleaning pipeline.</p>", unsafe_allow_html=True)

                uploaded_file = st.file_uploader("Upload File", type=['parquet', 'csv'], label_visibility="collapsed", key='raw_upload')
                
                if uploaded_file is not None:
                    with st.spinner("If this takes too long, blame the developer..."):
                        if uploaded_file.name.endswith('.parquet'):
                            st.info("Parquet file detected. Preparing tools…")
                            time.sleep(2)
                            st.session_state.raw_df = pd.read_parquet(uploaded_file)
                        else:
                            st.info("CSV file detected. Preparing tools…")
                            time.sleep(2)
                            st.session_state.raw_df = pd.read_csv(uploaded_file)
                        
                        report, needs_repair = PipelineProcessor.validate(st.session_state.raw_df)
                        st.session_state.validation_report = report
                        st.session_state.clean_df = None 
                        st.rerun()

            with st.container():
                st.markdown("<h3 style='text-align: center;'>OR</h3>", unsafe_allow_html=True)

            with st.container(border=True):
                st.markdown("<h3 style='text-align: center;'>Import Cleaned Dataset</h3>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: #666;'>Upload a previously cleaned dataset to bypass preparation.</p>", unsafe_allow_html=True)

                clean_file = st.file_uploader("Upload File", type=['csv'], label_visibility="collapsed", key='clean_upload')
                
                if clean_file is not None:
                    with st.spinner("Loading cleaned dataset..."):
                        st.session_state.analysis_raw_df = pd.read_csv(clean_file)
                        st.rerun()
    else:
        with st.sidebar:
            st.markdown("### Preprocessing Controls")
            
            joint_cols = [col for col in st.session_state.raw_df.columns if col.startswith('j')] if st.session_state.raw_df is not None else []
            selected_joint = st.selectbox("Select Target Node:", options=joint_cols)
            
            st.markdown("**Filters & Repair**")
            chk_teleport = st.checkbox("Remove Teleportation", value=True)
            spn_tele_thresh = st.number_input("Distance Threshold:", min_value=0.01, max_value=10.0, value=0.5, step=0.1)
            chk_repair = st.checkbox("Interpolate Missing Data", value=True)
            sel_repair_method = st.selectbox("Interpolation Method:", ["Linear", "Spline"], index=0)
            spn_repair_limit = st.number_input("Max Gap Size (Frames):", min_value=1, max_value=300, value=30, step=10)
            
            st.markdown("**Smoothing**")
            chk_smooth = st.checkbox("Apply Moving Average (Smoothing Jitter)", value=True)
            spn_win = st.number_input("Window Size:", min_value=3, max_value=101, value=3, step=2)

            st.write("")
            
            if st.button("Apply DSP Pipeline", type="primary", width='stretch'):
                df = st.session_state.raw_df.copy()
                with st.spinner("Running DSP Pipeline..."):
                    if chk_teleport: df, _ = PipelineProcessor.remove_teleportation(df, threshold=spn_tele_thresh)
                    if chk_repair: df = PipelineProcessor.repair(df, method=sel_repair_method.lower(), limit=spn_repair_limit)
                    if chk_smooth: df = PipelineProcessor.smooth(df, window=(spn_win if spn_win % 2 != 0 else spn_win + 1))
                    st.session_state.clean_df = df
                st.success("Pipeline executed successfully!")

            if st.session_state.clean_df is not None:
                st.write("")
                csv_buffer = st.session_state.clean_df.to_csv(index=False).encode('utf-8')
                st.download_button(label="Export Clean Dataset", data=csv_buffer, file_name="cleaned_kinematics.csv", mime="text/csv", width="stretch")
                
                if st.button("Analyze Data →", type="primary", width="stretch"):
                    st.session_state.analysis_raw_df = st.session_state.clean_df.copy()
                    st.rerun()

            st.divider()
            
            if st.button("Clear Workspace", width='stretch'):
                st.session_state.raw_df = None
                st.session_state.clean_df = None
                st.session_state.validation_report = ""
                st.rerun()

        if st.session_state.validation_report:
            with st.container(border=True):
                st.markdown("##### Validation Log")
                st.code(st.session_state.validation_report, language="text")

        if st.session_state.raw_df is not None and selected_joint:
            with st.container(border=True):
                fig = go.Figure()
                fig.add_trace(go.Scatter(y=st.session_state.raw_df[selected_joint], mode='lines', name='Raw Data', line=dict(color=COLOR_RAW_DATA, width=PREP_RAW_WIDTH, dash='dot')))
                
                if st.session_state.clean_df is not None:
                    fig.add_trace(go.Scatter(y=st.session_state.clean_df[selected_joint], mode='lines', name='Cleaned Data', line=dict(color=COLOR_CLEAN_DATA, width=PREP_CLEAN_WIDTH)))
                    
                fig.update_layout(
                    title=f"Data Quality Check. Joint: {selected_joint}", 
                    xaxis_title="Frames", 
                    yaxis_title="Coordinate Value (Meters)", 
                    hovermode="x unified", 
                    height=600, 
                    margin=dict(l=0, r=0, t=40, b=0)
                )
                
                st.plotly_chart(fig, width='stretch')

# =====================================================================
# VIEW: GAIT DASHBOARD
# =====================================================================

def render_dashboard():
    """Renders the final Kinematics Dashboard."""
    st.write('')
    if st.button("← Back to Hub", type='tertiary'):
        st.session_state.current_page = "hub"
        st.rerun()

    st.markdown("<h2 style='margin-top: -15px;'>Gait Analysis Dashboard</h2>", unsafe_allow_html=True)

    df_analysis_raw = st.session_state.analysis_raw_df

    with st.spinner("Running calculations..."):
        ts_df, df_per_sec, df_per_min, stats_df = process_analysis_data(df_analysis_raw)

    with st.sidebar:
        st.markdown("### Dashboard Controls")
        grouping = st.radio("Temporal Grouping:", ["Frames (Raw)", "Seconds", "Minutes"], index=1)
        
        show_env = st.checkbox("Show Variance Envelopes", value=True)
        env_win = st.number_input("Envelope Window Size:", min_value=1, max_value=100, value=5) if show_env else 1
        show_trend = st.checkbox("Show Linear Trendlines", value=True)
        show_rom = st.checkbox("Show Range of Motion (ROM)", value=False)
        
        st.divider()

        st.markdown("### Export Reports")
        export_df = ts_df if "Frames" in grouping else (df_per_sec if "Seconds" in grouping else df_per_min)
        
        csv_ts = export_df.to_csv(index=False).encode('utf-8')
        st.download_button(label="Download Timeseries Data", data=csv_ts, file_name=f"timeseries_{grouping.split(' ')[0].lower()}.csv", mime="text/csv", width='stretch')
        
        csv_stats = stats_df.to_csv(index=True).encode('utf-8')
        st.download_button(label="Download Summary Stats", data=csv_stats, file_name="summary_stats.csv", mime="text/csv", width='stretch')

        st.divider()
        if st.button("Process Raw Data", use_container_width=True):
            st.session_state.analysis_raw_df = None
            st.rerun()

        if st.button("Clear Workspace", use_container_width=True, type="primary"):
            st.session_state.raw_df = None
            st.session_state.clean_df = None
            st.session_state.analysis_raw_df = None
            st.session_state.current_page = "hub"
            st.rerun()

    if "Frames" in grouping:
        plot_df = ts_df.copy()
        x_col = "frame"
        if len(plot_df) > 1500: plot_df = plot_df.iloc[::len(plot_df)//1500]
    elif "Seconds" in grouping:
        plot_df = df_per_sec
        x_col = "time_sec"
    else:
        plot_df = df_per_min
        x_col = "time_min"

    with st.container(border=True):
        st.markdown("##### Metrics Data Table")
        st.dataframe(stats_df, use_container_width=True, height=250)

    st.markdown("### Postural Kinematics")
    
    with st.container(border=True):
        fig_lean = create_kinematic_plot(plot_df, x_col, ['lean_x'], ["Sagittal Trunk Lean"], [COLOR_RIGHT], "Trunk Lean Dynamics", show_env, show_trend, env_win)
        st.plotly_chart(fig_lean, width='stretch')
        
    with st.container(border=True):
        fig_drift = create_kinematic_plot(plot_df, x_col, ['drift_x'], ["Horizontal Position (X)"], [COLOR_CENTER], "Treadmill Drift (X-Axis)", show_env, show_trend, env_win, "Meters (m)")
        st.plotly_chart(fig_drift, width='stretch')
        
    # Vertical Oscillation (Cadence) Full Width
    with st.container(border=True):
        fig_cadence = create_kinematic_plot(plot_df, x_col, ['ankle_dist'], ["Inter-Ankle Distance"], ["#2ca02c"], "Stride Cadence (Ankle Distance)", show_env, show_trend, env_win, "Meters (m)")
        st.plotly_chart(fig_cadence, width='stretch')

    st.markdown("---")
    st.markdown("### Joint Kinematics")
    
    plots_config = [
        ("Knee Flexion", ['l_knee', 'r_knee'], ["Left Knee", "Right Knee"]),
        ("Hip Flexion", ['l_hip', 'r_hip'], ["Left Hip", "Right Hip"]),
        ("Shoulder Swing", ['l_sho', 'r_sho'], ["Left Shoulder", "Right Shoulder"]),
        ("Elbow Flexion", ['l_elb', 'r_elb'], ["Left Elbow", "Right Elbow"])
    ]

    cols = st.columns(2)
    for i, (title, y_cols, names) in enumerate(plots_config):
        if show_rom:
            y_cols = [f"{c}_rom" for c in y_cols]
            title = f"{title} (ROM)"
            
        with cols[i % 2]:
            with st.container(border=True):
                fig = create_kinematic_plot(plot_df, x_col, y_cols, names, [COLOR_LEFT, COLOR_RIGHT], title, show_env, show_trend, env_win)
                st.plotly_chart(fig,  width='stretch')

# =====================================================================
# MODULE ENTRY POINT
# =====================================================================
def render():
    """Routes the user based on whether they have prepared their dataset."""
    if st.session_state.get('analysis_raw_df') is not None:
        render_dashboard()
    else:
        render_preparation()
