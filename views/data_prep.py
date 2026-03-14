import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.math.filters import PipelineProcessor

def render():
    col_back, col_title = st.columns([1, 10])
    with col_back:
        if st.button("⬅️ Back to Menu", width='stretch'):
            st.session_state.current_page = "launcher"
            st.rerun()
    with col_title:
        st.title("🧹 Data Preparation")

    with st.sidebar:
        st.title("Controls")
        st.subheader("DATA SOURCE")
        uploaded_file = st.file_uploader("Select File (.parquet or .csv)", type=['parquet', 'csv'], key="prep_uploader")
        
        if uploaded_file is not None and st.session_state.raw_df is None:
            if uploaded_file.name.endswith('.parquet'):
                st.session_state.raw_df = pd.read_parquet(uploaded_file)
            else:
                st.session_state.raw_df = pd.read_csv(uploaded_file)
            
            report, needs_repair = PipelineProcessor.validate(st.session_state.raw_df)
            st.session_state.validation_report = report
            st.session_state.clean_df = None 
            st.rerun()

        st.markdown("---")
        st.subheader("PLOT PREVIEW")
        joint_cols = [col for col in st.session_state.raw_df.columns if col.startswith('j')] if st.session_state.raw_df is not None else []
        selected_joint = st.selectbox("Select Joint to Preview:", options=joint_cols)

        st.markdown("---")
        st.subheader("CLEANING PIPELINE")
        chk_teleport = st.checkbox("Remove Joint Teleportation", value=True)
        spn_tele_thresh = st.number_input("Distance Threshold:", min_value=0.01, max_value=10.0, value=0.5, step=0.1)
        chk_repair = st.checkbox("Interpolate Missing Data", value=True)
        chk_smooth = st.checkbox("Apply Moving Average", value=True)
        spn_win = st.number_input("Window Size:", min_value=3, max_value=101, value=3, step=2)

        if st.button("PREVIEW PIPELINE", type="primary", width='stretch', disabled=(st.session_state.raw_df is None)):
            df = st.session_state.raw_df.copy()
            with st.spinner("Running DSP Pipeline..."):
                if chk_teleport: df, _ = PipelineProcessor.remove_teleportation(df, threshold=spn_tele_thresh)
                if chk_repair: df = PipelineProcessor.repair(df)
                if chk_smooth: df = PipelineProcessor.smooth(df, window=(spn_win if spn_win % 2 != 0 else spn_win + 1))
                st.session_state.clean_df = df
            st.success("✅ Pipeline Applied!")

        st.markdown("---")
        if st.session_state.clean_df is not None:
            csv_buffer = st.session_state.clean_df.to_csv(index=False).encode('utf-8')
            st.download_button(label="EXPORT CLEAN CSV", data=csv_buffer, file_name="cleaned_kinematics_data.csv", mime="text/csv", width='stretch')

    if st.session_state.validation_report:
        with st.expander("Console Log / Health Check", expanded=True):
            st.code(st.session_state.validation_report, language="text")

    if st.session_state.raw_df is not None and selected_joint:
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=st.session_state.raw_df[selected_joint], mode='lines', name='Raw Data', line=dict(color='#D83B01', width=1.5, dash='dot')))
        if st.session_state.clean_df is not None:
            fig.add_trace(go.Scatter(y=st.session_state.clean_df[selected_joint], mode='lines', name='Cleaned Data', line=dict(color='#107C10', width=2.5)))
        fig.update_layout(title=f"Tracking: {selected_joint}", xaxis_title="Frames", yaxis_title="Coordinate Value (Meters)", hovermode="x unified", height=600, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("👈 Upload data from the left sidebar to begin.")