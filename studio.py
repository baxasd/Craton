import streamlit as st

# Import our modular page views
from core.pages import hub, prep, analysis, radar, viz

# ─── PAGE SETUP ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="OST Studio", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>    
    /* 2. KILL THE TOP PADDING */
    .block-container {
        padding-top: 2rem !important; 
        padding-bottom: 1rem !important;
    }
            
    [data-testid="stSidebarUserContent"] {
        padding-top: 0rem !important;
    }
    [data-testid="stSidebarHeader"] {
        padding: 0rem !important;   
            margin: 0rem; !important
    }       
    
    /* 4. Make sure all native cards stay solid white across the app */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

 
# ─── APP STATE ROUTER ────────────────────────────────────────────────────────
if 'current_page' not in st.session_state:
    st.session_state.current_page = "hub"

# Global data states shared across pages
if 'raw_df' not in st.session_state: st.session_state.raw_df = None
if 'clean_df' not in st.session_state: st.session_state.clean_df = None
if 'validation_report' not in st.session_state: st.session_state.validation_report = ""

# ─── NAVIGATION ENGINE ───────────────────────────────────────────────────────
if st.session_state.current_page == "hub":
    hub.render()
elif st.session_state.current_page == "prep":
    prep.render()
elif st.session_state.current_page == "analysis":
    analysis.render()
elif st.session_state.current_page == "radar":
    radar.render()
elif st.session_state.current_page == "viz":
    viz.render()