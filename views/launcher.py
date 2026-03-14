import streamlit as st

def render():
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
    st.title("OST Studio")
    st.markdown("Select a module to begin.")
    
    # 2x2 Grid Layout
    r1c1, r1c2 = st.columns(2, gap="large")
    with r1c1:
        st.info("### 🧹 Data Preparation\nTrim, clean, and apply DSP filters to raw Parquet recordings.")
        if st.button("Launch Data Prep", type="primary", width='stretch'):
            st.session_state.current_page = "data_prep"
            st.rerun()
            
    with r1c2:
        st.info("### 📊 Gait Analysis\nRun the kinematic engine, calculate postural drift, and export reports.")
        if st.button("Launch Analysis", type="primary", width='stretch'):
            st.session_state.current_page = "analysis"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    r2c1, r2c2 = st.columns(2, gap="large")
    
    with r2c1:
        st.info("### 🦴 Frame Inspector\nScrub through the timeline to view 2D kinematics frame-by-frame.")
        if st.button("Launch Visualizer", type="primary", width='stretch'):
            st.session_state.current_page = "visualizer"
            st.rerun()

    with r2c2:
        st.info("### 📡 Radar Analysis\nGenerate Micro-Doppler spectrograms and extract cadence.")
        if st.button("Launch Radar", type="primary", width='stretch'):
            st.session_state.current_page = "radar"
            st.rerun()