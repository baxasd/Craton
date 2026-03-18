# OST Suite 

<p align="left"><img src="assets/logo.png" alt="OST Suite Logo" width="250"></p>

#### Osteo-Skeletal Tracker & Telemetry

OST Suite is a high-performance, distributed workstation for recording, processing, and visualizing multi-modal skeletal kinematics and micro-Doppler radar data. 

![Version](https://img.shields.io/badge/version-0.3.0--beta.1-orange)
![Python](https://img.shields.io/badge/python-3.11-green)
![ZeroMQ](https://img.shields.io/badge/ZeroMQ-Curve25519-red)

> **⚠️ Beta Release:** Version 0.3.0-beta.1 introduces standalone `.exe` packaging. Please report any bugs or errors in the Issues tab.

---

## The Three Core Modules

### 🛰️ OST Streamer
The hardware-interfacing node. Captures and encrypts live radar and camera telemetry.

### 🖥️ OST Viewer
The live monitoring dashboard. High-speed visualization of encrypted network streams.

### 🧪 OST Studio
The offline analysis laboratory. A specialized workbench for post-processing recorded `.parquet` sessions.

---

## Quick Start (Standalone Beta)

1. **Download:** Get the latest release `.zip` and extract it.
2. **Configure:** Rename `settings-template.ini` to `settings.ini` inside libs directory.
3. **Security Keys:** Run the Keygen tool through `Studio.exe` to generate Curve25519 keys. Paste the output into your `settings.ini`.
4. **Launch:** Launch modules

---

## Running the Suite

Ensure your hardware is plugged in and `settings.ini` has the correct COM ports and IPs defined.

* **Start Hardware Capture:** Launch **Streamer**. *(Note: Radar and Camera streams should be run in separate terminals or computers).*
* **Watch Live Feed:** Launch **Viewer** to monitor the encrypted network stream.
* **Analyze Recorded Data:** Launch **Studio** to analyze saved data files offline.

---

## Developer Setup

If you prefer to run from source code:

1. Clone the repository and create a Python 3.11 virtual environment.
2. `pip install -r requirements.txt`
3. Generate keys: `python core/studio/keys.py`
4. Setup `settings.ini` as described at the beginning of this file
4. Run modules directly