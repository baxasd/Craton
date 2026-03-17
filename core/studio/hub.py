import streamlit as st
from core.ui.theme import LOGO_PATH

def render():
    # Hide the sidebar for a focused, distraction-free hub
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)

    # ── THE 1-3-1 BENTO LAYOUT ──
    _, center_col, _ = st.columns([1, 3, 1])

    with center_col:
        
        st.image(LOGO_PATH, width=150)
        st.markdown("##### Osteo-Skeletal Tracker Suite")
        st.caption("Select an analytical module to begin your workflow.")

        # ── ROW 1 ──
        r1_c1, r1_c2 = st.columns(2)
        
        with r1_c1:
            with st.container(border=True):
                st.markdown("### Data Prep")
                st.caption("Clean, trim, and filter raw kinematics.")
                if st.button("Launch Module", key="btn_prep", type="primary", width="stretch"):
                    st.session_state.current_page = "prep"
                    st.rerun()
                    
        with r1_c2:
            with st.container(border=True):
                st.markdown("### Gait Analysis")
                st.caption("Calculate posture metrics and export results.")
                if st.button("Launch Module", key="btn_gait", type="primary", width="stretch"):
                    st.session_state.current_page = "analysis"
                    st.rerun()

        # ── ROW 2 ──
        r2_c1, r2_c2 = st.columns(2)
        
        with r2_c1:
            with st.container(border=True):
                st.markdown("### Motion Lab")
                st.caption("View captured skeleton")
                if st.button("Launch Module", key="btn_viz", type="primary", width="stretch"):
                    st.session_state.current_page = "viz"
                    st.rerun()

        with r2_c2:
            with st.container(border=True):
                st.markdown("### Spectrogram Analysis")
                st.caption("Generate Micro-Doppler spectrograms.")
                if st.button("Launch Module", key="btn_radar", type="primary", width="stretch"):
                    st.session_state.current_page = "radar"
                    st.rerun()