import streamlit as st
from src.utils.theme import LOGO_PATH

def render():
     
    # Hide Sidebar in the Hub
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)

    # Main layout
    _, center_col, _ = st.columns([1, 8, 1])

    with center_col:
        
        # Logo and Tagline
        st.image(LOGO_PATH, width=200)
        st.markdown("<p style='font-weight: bold; color: #666; font-size: 0.9rem; margin-top: -10px; '>The Core of Motion</p>", unsafe_allow_html=True)

        # Layout inside the card
        main_col, action_col = st.columns([7, 3], gap="medium")

        with main_col:
            
            st.markdown("#### Welcome to Craton Studio")
            st.markdown("""  
                A unified workspace for human movement analysis.    
                Craton integrates 3D skeletal tracking with Radar Micro-Doppler analysis to understand complex gait dynamics. 

                Select a module to begin.
                """)
            
            st.write("")
            
            # System Architecture section
            st.markdown("#### System Architecture")
            hw_col, sw_col = st.columns(2)
            
            with hw_col:
                with st.container(border=True):
                    st.markdown("**Hardware Sensors**")
                    st.markdown("""
                    - **RGB-D Camera:** Intel RealSense D435i
                    - **mmWave Radar:** TI IWR6843
                    - **Telemetry:** ZeroMQ (Curve25519)
                    """)
            with sw_col:
                with st.container(border=True):
                    st.markdown("**Software Stack**")
                    st.markdown("""
                    - **Frontend:** Streamlit & PyQt6
                    - **Kinematics:** MediaPipe 0.10.21
                    - **DSP Engine:** SciPy & NumPy
                    """)

            st.write("")

            # Credits Section
            st.markdown("#### Acknowledgements")
            
            st.info("""
            **Institution:** University of Roehampton  
            **Research Teams:** CEBE, School of Health and Life Sciences   
            **Advisors:** Jose Peredes, Lisa Haskel  
            **Development:** Source Code and binary executables can be found here: [GitHub](https://github.com/baxasd/craton).  
            **License:** This software is open-source and released under the [MIT License](https://opensource.org/licenses/MIT).   
            *Developed in partial fulfillment of the requirements for the Bachelor of Science in Computer Science.*   
            """)

        # Individual Modules Containers
        with action_col:
            st.markdown("#### Modules")
            
            # Preprocessing
            with st.container(border=True, gap='xsmall'):
                st.markdown("##### Data Prep")
                st.caption("Clean, trim, and filter raw datasets.")
                if st.button("Launch", key="btn_prep", type="primary", width='stretch'):
                    st.session_state.current_page = "prep"
                    st.rerun()
                
            # Analysis
            with st.container(border=True, gap='xsmall'):
                st.markdown("##### Gait Analysis")
                st.caption("Calculate posture metrics and export.")
                if st.button("Launch", key="btn_gait", type="primary", width='stretch'):
                    st.session_state.current_page = "analysis"
                    st.rerun()

            # Visualization
            with st.container(border=True, gap='xsmall'):
                st.markdown("##### Motion Lab")
                st.caption("View captured motion and 2D tracking.")
                if st.button("Launch", key="btn_viz", type="primary", width='stretch'):
                    st.session_state.current_page = "viz"
                    st.rerun()

            # mmWave analysis
            with st.container(border=True, gap='xsmall'):
                st.markdown("##### Radar Analysis")
                st.caption("Analyze micro-Doppler spectrograms.")
                if st.button("Launch", key="btn_radar", type="primary", width='stretch'):
                    st.session_state.current_page = "radar"
                    st.rerun()