# 0.1.0

- Combination of Visualization and Preparation pipelines
- Launcher added to launch tools
- Core package layout overhaul
- Backend and Frontend separation

## 0.2.0

- Migration to Parquet from CSV file
- Smoothing Functions has been changed from Savgol to Moving Average
- Preprocessing Preview added to OST Studio
- Metadata Reading has been fixed for visualization

## 0.2.1

- Added metrics export in Studio
- Minor UI fix and tweaks
- Complete restructure of code package

## 0.2.2

- Code decoupled of Studio and Record applications into packages
- Major UI fixes
- Switched to Light Theme
- Added Analysis Page in Studio

## 0.3.0-beta.1

- Migrated Studio to Streamlit
- Added Radar Recorder and Spectrogram analyzer
- Changed Recorders into headless CLI applications
- Packaged all apps into a single executable build
- Added unified CLI launcher
- Centralized UI themes and configurations
- Secured network settings to local access only

## 0.3.1-beta.1

- Separated Secure Key generation
- Now the settings scope has been changed to root level
- Settings.ini file now can be generated automatically 

## 0.3.2-beta.1

- Fixed `settings.ini` and `records/` path resolution in compiled EXE mode
- Added QR Code to Studio login screen for easy local network access
- Added automatic local IP detection utility
- Improved directory structure handling for portable builds

# 1.0.0

- First stable release of OST Suite
- Finalized portable directory architecture
- Production-ready Studio authentication with remote access
- Consolidated multi-modal recording and analysis pipeline
 