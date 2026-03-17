import streamlit as st
import configparser

# Import our modular page views
from core.studio import hub, prep, analysis, radar, viz


# ─── PAGE SETUP ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="OST Studio", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>    
    .block-container { padding-top: 2rem !important; padding-bottom: 1rem !important; }
    [data-testid="stSidebarUserContent"] { padding-top: 0rem !important; }
    [data-testid="stSidebarHeader"] { padding: 0rem !important; margin: 0rem !important; }       
    }
</style>
""", unsafe_allow_html=True)

# Load global configuration to fetch the studio password
config = configparser.ConfigParser(interpolation=None)
config.read('settings.ini')
STUDIO_PASS = config.get('Security', 'studio_password', fallback='admin')

# Auth
def check_password():
    """Renders a centered login card and verifies the passcode."""
    if st.session_state.get("password_correct", False):
        return True

    # Hide sidebar during login for a cleaner look
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)

    # Use columns to force the login card into the center of the screen
    _, center_col, _ = st.columns([2, 1.5, 2]) 
    
    with center_col:
        with st.container(border=True):
            st.markdown("<h3 style='text-align: center;'>🔒 OST Studio Login</h3>", unsafe_allow_html=True)
            st.write("") # Quick spacer
            
            pwd = st.text_input("Enter Passcode:", type="password")
            
            if pwd == STUDIO_PASS:  
                st.session_state["password_correct"] = True
                st.rerun()
            elif pwd:
                st.error("Incorrect passcode.")
    
    return False

# Stop execution if not authenticated
if not check_password():
    st.stop()


# ─── SECURE APP ROUTER (Only runs if unlocked) ───────────────────────────────
with st.sidebar:
    st.image("assets/logo-main-transp.png", width=150)

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