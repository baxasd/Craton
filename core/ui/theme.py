import os
import sys
import configparser

# =============================================================================
# GLOBAL COLOR PALETTE & UI CONSTANTS
# =============================================================================

# ── Anatomy & Global Sides ──
COLOR_LEFT = "#005FB8"     # Blue (Used for left limbs and Frontal lean)
COLOR_RIGHT = "#D83B01"    # Orange (Used for right limbs and Sagittal lean)
COLOR_CENTER = "#8764B8"   # Purple (Used for the calculated spine/trunk)

# ── Data Preparation Tab ──
COLOR_RAW_DATA = "#D83B01"   # Orange/Red for raw, noisy data
COLOR_CLEAN_DATA = "#107C10" # Green for smooth, filtered data
PREP_RAW_WIDTH = 1.5
PREP_CLEAN_WIDTH = 2.5

# ── Visualizer Tab ──
COLOR_JOINT = "#323130"               # Dark gray for joint markers
COLOR_SKELETON_BG = "rgba(0,0,0,0.02)"# Faint gray background for the 2D canvas
COLOR_REF_LINE = "rgba(0,0,0,0.15)"   # Faint tracking line that follows the hips
VIZ_BONE_WIDTH = 3
VIZ_SPINE_WIDTH = 5

# ── Radar Tab ──
COLOR_RADAR_BG = "rgba(0,0,0,1)"             # Pure black background for spectrogram
COLOR_CENTROID_MAIN = "#00E5FF"              # Cyan line for mass centroid
COLOR_CENTROID_SHADOW = "black"              # Drop shadow to make the cyan pop
COLOR_ZERO_LINE = "rgba(255, 255, 255, 0.4)" # Faint white dashed line at 0 m/s

TEXT_DIM = "#888888"                         # Dim gray for text labels

# ── CLEAN UI CONSTANTS ───────────────────────────────────────────────────────
COLOR_MAIN_BG  = "#FFFFFF"  # Pure white background
COLOR_TEXT     = "#333333"  # Crisp dark gray text


# ─── 1. BULLETPROOF PATH RESOLUTION ───
if getattr(sys, 'frozen', False):
    # PyInstaller put everything inside the 'libs' folder!
    ROOT_DIR = os.path.join(sys._MEIPASS, 'libs')
else:
    # If running from source (core/ui/themes.py), go up two levels to reach root
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.abspath(os.path.join(_current_dir, '..', '..'))

# Safely construct absolute paths
SETTINGS_PATH = os.path.join(ROOT_DIR, 'settings.ini')
LOGO_PATH = os.path.join(ROOT_DIR, 'assets', 'logo.png')
ICON_PATH = os.path.join(ROOT_DIR, 'assets', 'icon.ico')
COMMAND_ICON = os.path.join(ROOT_DIR, 'assets', 'command.ico')

# ─── 2. LOAD CONFIGURATIONS ───
config = configparser.ConfigParser(interpolation=None)
config.read(SETTINGS_PATH)

# Export our global variables
APP_VERSION = "v0.3.0"
STUDIO_PASS = config.get('Security', 'studio_password', fallback='admin')