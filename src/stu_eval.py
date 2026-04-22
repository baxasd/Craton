import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import io_types as structs
import math_motion as kinematics
from ui_theme import COLOR_LEFT, COLOR_RIGHT

# Perform Calculations and Grouping
@st.cache_data(show_spinner=False)
def process_analysis_data(df_raw):
    session = structs.df_to_session(df_raw)
    ts_df, _ = kinematics.generate_analysis_report(session)
    
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

    return ts_df, df_per_sec, df_per_min, stats_df

# Creates Plotly plots
def create_kinematic_plot(df, x_col, y_cols, names, colors, title, show_env=False):
    fig = go.Figure()
    window_size = max(1, len(df)//20) if show_env else 1

    for y_col, name, color in zip(y_cols, names, colors):
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

    fig.update_layout(
        title=title, xaxis_title=x_col.capitalize(), yaxis_title="Degrees (°)",
        hovermode="x unified", margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

# Main UI Logic
def render():
    # Title and Navigation
    st.write("")
    if st.button("← Back to Hub", type="tertiary"):
        st.session_state.current_page = "hub"
        st.rerun()
    st.markdown("<h2 style='margin-top: -15px;'>Gait Analysis</h2>", unsafe_allow_html=True)
    
    if st.session_state.get('analysis_raw_df') is None:

        # Remove Sidebar if file is uploaded
        st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
        
        # Main Layout for Upload file Container
        _, center_col, _ = st.columns([1, 2, 1])
        
        # File Uploader Definition
        with center_col:
            with st.container(border=True):
                st.markdown("<h3 style='text-align: center;'>Import Cleaned Dataset</h3>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: #666;'>Upload a preprocessed file to generate the analysis report.</p>", unsafe_allow_html=True)
                
                analysis_file = st.file_uploader("Upload File", type=['csv', 'parquet'], label_visibility="collapsed")
                
                if analysis_file is not None:
                    with st.spinner("Loading the dataset..."):
                        if analysis_file.name.endswith('.parquet'): 
                            st.info("Parquet file detected. Preparing tools…")
                            time.sleep(2)
                            st.session_state.analysis_raw_df = pd.read_parquet(analysis_file)
                        else: 
                            st.info("CSV file detected. Preparing tools…")
                            time.sleep(2)
                            st.session_state.analysis_raw_df = pd.read_csv(analysis_file)
                        st.rerun()

    # Shows up only when Data is Loaded
    else:
        # Fetch the loaded data
        df_analysis_raw = st.session_state.analysis_raw_df

        # Wrapped with spinner to prevent exposing function names
        with st.spinner("Running calculations..."):
            ts_df, df_per_sec, df_per_min, stats_df = process_analysis_data(df_analysis_raw)

        # Sidebar configs
        with st.sidebar:
            st.markdown("### Visualization Controls")
            grouping = st.selectbox("Resolution:", ["Frames", "Seconds", "Minutes"], index=1)
            show_env = st.checkbox("Show Variance Envelopes", value=True)
            
            st.divider()

            # Export Section
            st.markdown("### Export Reports")
            export_df = ts_df if "Frames" in grouping else (df_per_sec if "Seconds" in grouping else df_per_min)
            
            # Download Grouped Data
            st.download_button(
                label=f"Download Aggregated Data",
                data=export_df.to_csv(index=False).encode('utf-8'),
                file_name=f"timeseries_{grouping.split(' ')[0].lower()}.csv",
                mime='text/csv', width='stretch', type='primary'
            )
            
            # Downloads Summary
            st.download_button(
                label="Download Summary",
                data=stats_df.to_csv(index=True).encode('utf-8'),
                file_name="summary.csv",
                mime='text/csv', width='stretch', type='primary'
            )
            
            st.divider()

            # Clears current uploaded file
            if st.button("Clear Workspace", width='stretch'):
                st.session_state.analysis_raw_df = None
                st.rerun()

        # Main View after Data is Loaded
        with st.container(border=True):
            st.markdown("##### View Metrics Data Table")
            st.dataframe(stats_df.style.format("{:.2f}"), width='stretch', height=250)

        # Determine plotting dataframe based on grouping
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

        # Trunk Lean
        with st.container(border=True):
            fig_lean = create_kinematic_plot(plot_df, x_col, ['lean_x', 'lean_z'], ["Sagittal", "Frontal"], [COLOR_RIGHT, COLOR_LEFT], "Trunk Lean Dynamics", show_env)
            st.plotly_chart(fig_lean, width='stretch')

        # Charts 2-5: The 2x2 Grid
        plots_config = [
            ("Knee Flexion", ['l_knee', 'r_knee'], ["Left Knee", "Right Knee"]),
            ("Hip Flexion", ['l_hip', 'r_hip'], ["Left Hip", "Right Hip"]),
            ("Shoulder Swing", ['l_sho', 'r_sho'], ["Left Shoulder", "Right Shoulder"]),
            ("Elbow Flexion", ['l_elb', 'r_elb'], ["Left Elbow", "Right Elbow"])]
        
        # Chart Implementations
        cols = st.columns(2)
        for i, (title, y_cols, names) in enumerate(plots_config):
            with cols[i % 2]:
                with st.container(border=True):
                    fig = create_kinematic_plot(plot_df, x_col, y_cols, names, [COLOR_LEFT, COLOR_RIGHT], title, show_env)
                    st.plotly_chart(fig,  width='stretch')