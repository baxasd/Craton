import os
import sys
import configparser

COLOR_LEFT = "#005FB8"
COLOR_RIGHT = "#D83B01"
COLOR_CENTER = "#8764B8" 

# Data Preparation
COLOR_RAW_DATA = "#D83B01"
COLOR_CLEAN_DATA = "#107C10"
PREP_RAW_WIDTH = 1.5
PREP_CLEAN_WIDTH = 2.5

# Visualizer
COLOR_JOINT = "#323130"
COLOR_SKELETON_BG = "rgba(0,0,0,0.02)"
COLOR_REF_LINE = "rgba(0,0,0,0.15)"   
VIZ_BONE_WIDTH = 7
VIZ_SPINE_WIDTH = 7

# Radar Tab
COLOR_RADAR_BG = "rgba(0,0,0,1)"       
COLOR_CENTROID_MAIN = "#00E5FF"              
COLOR_CENTROID_SHADOW = "black"             
COLOR_ZERO_LINE = "rgba(255, 255, 255, 0.4)" 

if getattr(sys, 'frozen', False):
    ROOT_DIR = sys._MEIPASS
    BASE_DIR = os.path.dirname(sys.executable)
    SETTINGS_PATH = os.path.join(BASE_DIR, 'settings.ini')
else:
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.abspath(os.path.join(_current_dir, '..', '..'))
    BASE_DIR = ROOT_DIR
    SETTINGS_PATH = os.path.join(ROOT_DIR, 'settings.ini')

LOGO_PATH = os.path.join(ROOT_DIR, 'assets', 'logo.png')
ICON_PATH = os.path.join(ROOT_DIR, 'assets', 'icon.ico')
COMMAND_ICON = os.path.join(ROOT_DIR, 'assets', 'command.ico')

config = configparser.ConfigParser(interpolation=None)
config.read(SETTINGS_PATH)

APP_VERSION = "v1.0.0"
STUDIO_PASS = config.get('Security', 'studio_password', fallback='admin')