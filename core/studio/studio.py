# core/studio/studio.py
import streamlit as st

# 1. Import from our centralized themes file!
from core.ui.theme import LOGO_PATH, APP_VERSION, STUDIO_PASS, ICON_PATH
from core.studio import hub, prep, analysis, radar, viz

# ─── SET THE PAGE ICON ───
st.set_page_config(page_title="OST Studio", page_icon=ICON_PATH, layout="wide", 
                   initial_sidebar_state="expanded",
                   menu_items={'About': f"### OST Suite\n**Version:** {APP_VERSION}\n\nDeveloped for OST Lab."})

st.markdown("""<style>    
    .block-container { padding-top: 2rem !important; padding-bottom: 1rem !important; }
    [data-testid="stSidebarUserContent"] { padding-top: 0rem !important; }
    [data-testid="stSidebarHeader"] { padding: 0rem !important; margin: 0rem !important; }</style>""", unsafe_allow_html=True)

# ─── AUTHENTICATION ───
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
    _, center_col, _ = st.columns([2, 1.5, 2]) 
    
    with center_col:
        with st.container(border=True):
            st.markdown("## Login")

            pwd = st.text_input("Enter Passcode:", type="password")
            
            if pwd == STUDIO_PASS:  
                st.session_state["password_correct"] = True
                st.rerun()
            elif pwd:
                st.error("Incorrect passcode.")
    
    return False

if not check_password():
    st.stop()


# ─── SECURE APP ROUTER ───
with st.sidebar:
    st.image(LOGO_PATH, width=140, )

# Initialize States
if 'current_page' not in st.session_state: st.session_state.current_page = "hub"
if 'raw_df' not in st.session_state: st.session_state.raw_df = None
if 'clean_df' not in st.session_state: st.session_state.clean_df = None
if 'validation_report' not in st.session_state: st.session_state.validation_report = ""

# Navigation Engine
if st.session_state.current_page == "hub": hub.render()
elif st.session_state.current_page == "prep": prep.render()
elif st.session_state.current_page == "analysis": analysis.render()
elif st.session_state.current_page == "radar": radar.render()
elif st.session_state.current_page == "viz": viz.render()
