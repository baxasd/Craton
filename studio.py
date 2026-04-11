# core/studio/studio.py
import streamlit as st

from core.ui.theme import LOGO_PATH, APP_VERSION, STUDIO_PASS, ICON_PATH
from core.studio import hub, prep, analysis, radar, viz

st.set_page_config(page_title="Craton Studio", page_icon=ICON_PATH, layout="wide", 
                   initial_sidebar_state="expanded",
                   menu_items={'About': f"### Craton Studio\n**Version:** {APP_VERSION}\n\nDeveloped for Craton Suite"})

st.markdown("""<style>    
    .block-container { padding-top: 2rem !important; padding-bottom: 1rem !important; }
    [data-testid="stSidebarUserContent"] { padding-top: 0rem !important; }
    [data-testid="stSidebarHeader"] { padding: 0rem !important; margin: 0rem !important; }</style>""", unsafe_allow_html=True)

# ─── AUTHENTICATION ──
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
  
    st.write("")
    st.write("")
    st.write("")
    st.write("")
    st.write("")
    st.write("")

    _, center_col, _ = st.columns([1, 0.8, 1]) 
    
    with center_col:
        with st.container(border=True, gap='xxsmall'):
            
            # Left-aligned logo with a fixed pixel size (adjust 80 to your preference)
            st.image(LOGO_PATH, width=230)
            
            # Left-aligned text (removed text-align: center)
            st.markdown("<p style='font-weight: bold; color: #666; font-size: 0.9rem; '>The Core of Motion</p>", unsafe_allow_html=True)
            st.markdown("<p style='color: #242024; font-size: 1rem; margin-bottom: 10px; margin-top: 20px;'>Human Osteo Skeletal Tracking Suite</p>", unsafe_allow_html=True)
            
            with st.form("login_form", border=False):
                pwd = st.text_input("Enter Password", type="password", placeholder="Enter Passcode", label_visibility="hidden")

                submitted = st.form_submit_button("Sign In", type="primary", width='stretch')
                
                if submitted:
                    if pwd == STUDIO_PASS:  
                        st.session_state["password_correct"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect passcode. Please try again.")
        
            st.markdown("<p style='text-align: left; color: #999; font-size: 0.8rem; margin-top: 20px;'>Craton Suite &copy; 2026</p>", unsafe_allow_html=True)
    
    return False

if not check_password():
    st.stop()

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
