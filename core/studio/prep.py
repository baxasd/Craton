import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time
from core.math.filters import PipelineProcessor
from core.ui.theme import COLOR_RAW_DATA, COLOR_CLEAN_DATA, PREP_RAW_WIDTH, PREP_CLEAN_WIDTH

def render():
    st.write('')

    # Title and Navigation
    if st.button("← Back to Hub", type='tertiary'):
        st.session_state.current_page = "hub"
        st.rerun()
        
    # Page Title
    st.markdown("<h2 style='margin-top: -15px;'>Data Preparation</h2>", unsafe_allow_html=True)
    
    # Check if data is uploaded
    if st.session_state.get('raw_df') is None:
        
        st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
        
        # Layout for Upload Logic
        _, center_col, _ = st.columns([1, 2, 1])
        
        # Upload File Logic
        with center_col:
            with st.container(border=True):
                st.markdown("<h3 style='text-align: center;'>Import Dataset</h3>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: #666;'>Drag and drop your raw tracking data to begin preprocessing.</p>", unsafe_allow_html=True)

                # Upload Point
                uploaded_file = st.file_uploader("Upload File", type=['parquet', 'csv'], label_visibility="collapsed")
                
                # Necessary checks before any processing is done
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
    else:

        # Sidebar. It appears only when file is uploaded
        with st.sidebar:
            st.markdown("### Preprocessing Controls")
            
            # Joint Selection Drop Down Menu
            joint_cols = [col for col in st.session_state.raw_df.columns if col.startswith('j')] if st.session_state.raw_df is not None else []
            selected_joint = st.selectbox("Select Target Node:", options=joint_cols)
            
            # PreProcessing Parameters
            st.markdown("**Filters & Repair**")
            chk_teleport = st.checkbox("Remove Teleportation", value=True)
            spn_tele_thresh = st.number_input("Distance Threshold:", min_value=0.01, max_value=10.0, value=0.5, step=0.1)
            chk_repair = st.checkbox("Interpolate Missing Data", value=True)
            
            st.markdown("**Smoothing**")
            chk_smooth = st.checkbox("Apply Moving Average", value=True)
            spn_win = st.number_input("Window Size:", min_value=3, max_value=101, value=3, step=2)

            st.write("")
            
            # Apply Button. Initiates Preprocessing
            if st.button("Apply DSP Pipeline", type="primary", width='stretch'):
                df = st.session_state.raw_df.copy()
                with st.spinner("Running DSP Pipeline..."):
                    if chk_teleport: df, _ = PipelineProcessor.remove_teleportation(df, threshold=spn_tele_thresh)
                    if chk_repair: df = PipelineProcessor.repair(df)
                    if chk_smooth: df = PipelineProcessor.smooth(df, window=(spn_win if spn_win % 2 != 0 else spn_win + 1))
                    st.session_state.clean_df = df
                st.success("Pipeline executed successfully!")

            # Export Button. Appears only if the dataset is clean
            if st.session_state.clean_df is not None:
                st.write("")
                csv_buffer = st.session_state.clean_df.to_csv(index=False).encode('utf-8')
                st.download_button(label="Export Clean Dataset", data=csv_buffer, file_name="cleaned_kinematics.csv", mime="text/csv", width="stretch")

            st.divider()
            
            # Clear Data Button (To return to State 1)
            if st.button("Clear Workspace", width='stretch'):
                st.session_state.raw_df = None
                st.session_state.clean_df = None
                st.session_state.validation_report = ""
                st.rerun()

        # Main Window. It shows charts of to preview the dataset
        if st.session_state.validation_report:
            with st.container(border=True):
                st.markdown("##### Validation Log")
                st.code(st.session_state.validation_report, language="text")

        # Plotly Chart Integration
        if st.session_state.raw_df is not None and selected_joint:
            with st.container(border=True):
                fig = go.Figure()
                
                # Raw dataset
                fig.add_trace(go.Scatter(y=st.session_state.raw_df[selected_joint], mode='lines', name='Raw Data', line=dict(color=COLOR_RAW_DATA, width=PREP_RAW_WIDTH, dash='dot')))
                
                # Cleaned dataset
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