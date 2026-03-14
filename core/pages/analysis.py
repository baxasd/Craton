import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from core.io import structs
from core.math import kinematics
from core.ui.theme import COLOR_LEFT, COLOR_RIGHT

@st.cache_data
def process_analysis_data(df_raw):
    """Replicates the heavy math pipeline."""
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

def create_kinematic_plot(df, x_col, y_cols, names, colors, title, show_env=False):
    """Generates a Plotly chart with optional SD Variance Envelopes."""
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

def render():
    col_back, col_title = st.columns([1, 10])
    with col_back:
        if st.button("⬅️ Back to Menu", width='stretch'):
            st.session_state.current_page = "hub"
            st.rerun()
    with col_title:
        st.title("📊 Gait Analysis")

    with st.sidebar:
        st.title("Analysis Controls")
        st.subheader("DATA SOURCE")
        analysis_file = st.file_uploader("Upload CLEANED Data (.csv or .parquet)", type=['csv', 'parquet'], key="analysis_uploader")
        
        df_analysis_raw = None
        if analysis_file is not None:
            if analysis_file.name.endswith('.parquet'): df_analysis_raw = pd.read_parquet(analysis_file)
            else: df_analysis_raw = pd.read_csv(analysis_file)
        
        st.markdown("---")
        st.subheader("PLOT CONTROLS")
        grouping = st.selectbox("Resampling Level:", ["Frames (Raw)", "Seconds (Averaged)", "Minutes (Averaged)"], index=1)
        show_env = st.checkbox("Show Variance Envelopes (SD)", value=True)
        
        st.markdown("---")
        st.subheader("EXPORT REPORTS")
        if df_analysis_raw is not None:
            st.caption("Crunching math to enable exports...")
            ts_df, df_per_sec, df_per_min, stats_df = process_analysis_data(df_analysis_raw)
            
            export_df = ts_df if "Frames" in grouping else (df_per_sec if "Seconds" in grouping else df_per_min)
            st.download_button(
                label=f"📥 Download Timeline Data ({grouping.split(' ')[0]})",
                data=export_df.to_csv(index=False).encode('utf-8'),
                file_name=f"kinematics_timeline_{grouping.split(' ')[0].lower()}.csv",
                mime='text/csv', width='stretch'
            )
            
            st.download_button(
                label="📥 Download Summary Stats",
                data=stats_df.to_csv(index=True).encode('utf-8'),
                file_name="kinematics_summary_stats.csv",
                mime='text/csv', width='stretch'
            )

    if df_analysis_raw is not None:
        with st.expander("METRICS SUMMARY & POSTURAL DRIFT", expanded=True):
            st.dataframe(stats_df.style.format("{:.2f}"), use_container_width=True, height=250)

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

        # UI THEME CONSTANTS APPLIED HERE
        with st.container(border=True):
            fig_lean = create_kinematic_plot(plot_df, x_col, ['lean_x', 'lean_z'], ["Sagittal (X)", "Frontal (Z)"], [COLOR_RIGHT, COLOR_LEFT], "1. Trunk Lean Dynamics", show_env)
            st.plotly_chart(fig_lean, use_container_width=True)

        plots_config = [
            ("2. Knee Flexion", ['l_knee', 'r_knee'], ["Left Knee", "Right Knee"]),
            ("3. Hip Flexion", ['l_hip', 'r_hip'], ["Left Hip", "Right Hip"]),
            ("4. Shoulder Swing", ['l_sho', 'r_sho'], ["Left Shoulder", "Right Shoulder"]),
            ("5. Elbow Flexion", ['l_elb', 'r_elb'], ["Left Elbow", "Right Elbow"])
        ]
        
        cols = st.columns(2)
        for i, (title, y_cols, names) in enumerate(plots_config):
            with cols[i % 2]:
                with st.container(border=True):
                    fig = create_kinematic_plot(plot_df, x_col, y_cols, names, [COLOR_LEFT, COLOR_RIGHT], title, show_env)
                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("👈 Upload your CLEANED dataset from the Data Prep tab to run the analysis.")