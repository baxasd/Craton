import streamlit as st
from src.utils.theme import LOGO_PATH, APP_VERSION, STUDIO_PASS, ICON_PATH
from src.studio import hub as hub, gait as gait, radar as radar

# Global Page Config
st.set_page_config(page_title="Craton Studio", page_icon=ICON_PATH, layout="wide", 
                   initial_sidebar_state="expanded",menu_items={'About': f"### Craton Studio\n**Version:** {APP_VERSION}"})

# Global Layout Changes. Overrides default margins and paddings
st.markdown("""<style>    
    .block-container { padding-top: 2rem !important; padding-bottom: 1rem !important; }
    [data-testid="stSidebarUserContent"] { padding-top: 0rem !important; }
    [data-testid="stSidebarHeader"] { padding: 0rem !important; margin: 0rem !important; }</style>""", unsafe_allow_html=True)

# Simple Auth Logic. Uses PlainText password to protect software in Local Network
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    # Removes sidebar from Login Screen
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)

    # Custom Space to push Login Container to Center of the Screen
    st.write("")
    st.write("")
    st.write("")

    # Layout. Splits screen into 3 grid horizontally
    _, center_col, _ = st.columns([1, 0.8, 1]) 
    
    # Uses center cell to draw login container
    with center_col:
        with st.container(border=True, gap='xxsmall'):
            
            # Logo with Fixed Size
            st.image(LOGO_PATH, width=230)
            
            # SubTexts under the Logo
            st.markdown("<p style='font-weight: bold; color: #666; font-size: 0.9rem; '>The Core of Motion</p>", unsafe_allow_html=True)
            st.markdown("<p style='color: #242024; font-size: 1rem; margin-bottom: 10px; margin-top: 20px;'>Human Osteo Skeletal Tracking Suite (Craton)</p>", unsafe_allow_html=True)
            
            # Intentional form to wrap textbox and button to make the native Enter key work
            with st.form("login_form", border=False):
                pwd = st.text_input("Enter Password", type="password", placeholder="Enter Passcode", label_visibility="hidden")

                submitted = st.form_submit_button("Sign In", type="primary", width='stretch')
                
                if submitted:
                    if pwd == STUDIO_PASS:  
                        st.session_state["password_correct"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect passcode. Please try again.")


    return False

# Terminate if Check Password Failed
if not check_password():
    st.stop()

# Sets Logo for sidebar globally
with st.sidebar:
    st.image(LOGO_PATH, width=180)

# States of Pages
if 'current_page' not in st.session_state: st.session_state.current_page = "hub"
if 'raw_df' not in st.session_state: st.session_state.raw_df = None
if 'clean_df' not in st.session_state: st.session_state.clean_df = None
if 'validation_report' not in st.session_state: st.session_state.validation_report = ""
if 'analysis_raw_df' not in st.session_state: st.session_state.analysis_raw_df = None

# Navigation
if st.session_state.current_page == "hub": hub.render()
elif st.session_state.current_page == "gait": gait.render()
elif st.session_state.current_page == "radar": radar.render()
