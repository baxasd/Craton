# OST Suite 

<p align="left"><img src="assets/logo-main-transp.png" alt="OST Suite Logo" width="250"></p>

#### Osteo-Skeletal Tracker & Telemetry

OST Suite is a high-performance, distributed workstation for recording, processing, and visualizing multi-modal skeletal kinematics and micro-Doppler radar data. 

![Version](https://img.shields.io/badge/version-0.3.0-blue)
![Python](https://img.shields.io/badge/python-3.11-green)
![ZeroMQ](https://img.shields.io/badge/ZeroMQ-Curve25519-red)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.21-teal)

---

## The Three Core Modules

### OST Publisher (`stream.py`)
The hardware-interfacing node. 

### OST Viewer (`view.py`)
The live monitoring dashboard. 

### OST Studio (`studio.py`)
The offline analysis laboratory. Streamlit web app for post-processing recorded sessions.

---

## Quick Start Setup

**1. Clone the Repository & Create Virtual Environment**

**2. Install Dependencies** - install using requirements.txt

**3. Configure Settings** - Everything is managed in a central settings file. Copy the template to get started:

**4. Generate Security Keys**
Because OST encrypts all network traffic, you must generate a pair of cryptographic keys before streaming
*Copy the terminal output and paste it at the bottom of new `settings.ini` file.*

---

## Running the Suite

Ensure your hardware is plugged in and your `settings.ini` has the correct COM ports and IPs defined.

**Start the Hardware Capture:** - If running both radar and camera, it should be done in separate computers or terminals

**Watch the Live Feed:** - Make sure you have generated keypair for encyrption

**Analyze Recorded Data:** - Streamlit program offers to analyze parquet files offline
