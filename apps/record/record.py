import sys
import time
import datetime
import logging
import zmq
import json
import configparser
import cv2

from core.radar.base import parse_standard_frame
from core.config import VERSION
from core.storage import CameraSessionWriter, RadarSessionWriter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Publisher")

# ─────────────────────────────────────────────────────────────────────────────
#  Load Global Settings
# ─────────────────────────────────────────────────────────────────────────────
config = configparser.ConfigParser()
config.read('settings.ini')

HW_CFG_FILE = config['Hardware']['radar_cfg_file']
HW_CLI_PORT = config['Hardware']['cli_port']
HW_DATA_PORT = config['Hardware']['data_port']
ZMQ_RADAR_PORT = config['Network'].get('zmq_port', '5555')
ZMQ_CAM_PORT = config['Network'].get('zmq_camera_port', '5556')

# ─────────────────────────────────────────────────────────────────────────────
#  Hardware Connection Helpers
# ─────────────────────────────────────────────────────────────────────────────
def connect_radar():
    from sensors.radar import RadarSensor
    log.info("Connecting to Texas Instruments hardware...")
    
    cli, data = None, None
    if HW_CLI_PORT.lower() != 'auto' and HW_DATA_PORT.lower() != 'auto':
        cli, data = HW_CLI_PORT, HW_DATA_PORT
    else:
        log.info("Scanning for auto-assigned USB ports...")
        cli, data = RadarSensor.find_ti_ports()
    
    if not cli or not data:
        log.error("Auto-detection failed: No TI radar ports found. Please check connections.")
        return None

    log.info(f"Using CLI: {cli} | DATA: {data}")
    
    radar = RadarSensor(cli, data, HW_CFG_FILE)
    radar.connect_and_configure()
    
    print("\n" + "="*40)
    print(" RADAR CONFIGURATION LOADED")
    print("="*40)
    for key, value in radar.config.summary().items():
        print(f" {key:<20}: {value}")
    print("="*40 + "\n")
    
    return radar

# ─────────────────────────────────────────────────────────────────────────────
#  Stream Loops
# ─────────────────────────────────────────────────────────────────────────────
def run_radar_stream(zmq_context: zmq.Context, record: bool):
    radar = connect_radar()
    if radar is None: return

    # ONLY bind the Radar port if this function is actually called
    zmq_socket = zmq_context.socket(zmq.PUB)
    zmq_socket.bind(f"tcp://*:{ZMQ_RADAR_PORT}")

    writer = RadarSessionWriter(metadata=radar.config.summary()) if record else None
    
    if record: log.info(f"RECORD MODE: Broadcasting over ZMQ and saving to {writer.filepath}")
    else: log.info("PREVIEW MODE: Broadcasting over ZMQ only (No disk writing).")

    print("\n>>> RADAR STREAM ACTIVE. Press Ctrl+C to stop. <<<\n")
    
    try:
        while True:
            raw_bytes = radar.read_raw_frame()
            if raw_bytes is None:
                time.sleep(0.001)
                continue

            frame = parse_standard_frame(raw_bytes)
            rdhm = frame.get("RDHM")
            
            if rdhm is not None:
                zmq_socket.send(rdhm.tobytes())
                if record: writer.write_frame(rdhm)

    except KeyboardInterrupt:
        log.info("Ctrl+C detected. Stopping radar stream...")
    finally:
        radar.close()
        zmq_socket.close() # Safely release the port
        if writer: writer.close()
        time.sleep(0.5)


def run_camera_stream(zmq_context: zmq.Context, record: bool):
    log.info("Loading camera AI models...")
    from sensors.realsense import RealSenseCamera
    from core.depth import get_mean_depth, deproject_pixel_to_point
    from core.pose import PoseEstimator
    
    # ONLY bind the Camera port if this function is actually called
    zmq_socket = zmq_context.socket(zmq.PUB)
    zmq_socket.bind(f"tcp://*:{ZMQ_CAM_PORT}")

    writer = None
    if record:
        print("\n--- STARTING AUTOMATIC CAMERA RECORDING ---")
        subj = "Auto"
        act = "Camera"
        meta = {"Date": datetime.datetime.now().isoformat()}
        writer = CameraSessionWriter(subj, act, metadata=meta)
        log.info(f"RECORD MODE: Broadcasting over ZMQ and saving to {writer.filepath}")
    else:
        log.info("PREVIEW MODE: Broadcasting over ZMQ only.")

    cam = RealSenseCamera(width=640, height=480, fps=30)
    pose = PoseEstimator(model_complexity=1)

    print("\n>>> CAMERA STREAM ACTIVE. Press Ctrl+C to stop. <<<\n")
    try:
        while True:
            color_img, depth_frame = cam.get_frames()
            if color_img is None:
                continue

            h, w, _ = color_img.shape
            landmarks = pose.estimate(color_img)
            
            frame_data = {"timestamp": time.time()}
            depth_intrin = None

            if depth_frame:
                depth_intrin = depth_frame.profile.as_video_stream_profile().intrinsics

            if landmarks:
                for i, (lx, ly, lz) in enumerate(landmarks):
                    cx, cy = int(lx), int(ly)
                    if 0 <= cx < w and 0 <= cy < h:
                        cv2.circle(color_img, (cx, cy), 3, (0, 255, 0), -1)
                        
                        if depth_intrin:
                            dist = get_mean_depth(depth_frame, cx, cy, w, h)
                            if dist:
                                p = deproject_pixel_to_point(depth_intrin, cx, cy, dist)
                                frame_data[f"j{i}_x"] = p[0]
                                frame_data[f"j{i}_y"] = p[1]
                                frame_data[f"j{i}_z"] = p[2]

            ret, jpeg_buffer = cv2.imencode('.jpg', color_img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            
            if ret:
                zmq_socket.send_multipart([
                    json.dumps(frame_data).encode('utf-8'),
                    jpeg_buffer.tobytes()
                ])

            if record and writer:
                writer.write_frame(frame_data)

    except KeyboardInterrupt:
        log.info("Ctrl+C detected. Stopping camera stream...")
    finally:
        cam.stop()
        zmq_socket.close() # Safely release the port
        if writer: writer.close()

# ─────────────────────────────────────────────────────────────────────────────
#  Main Application Menu
# ─────────────────────────────────────────────────────────────────────────────
def main():
    context = zmq.Context()
    
    while True:
        print("\n=========================================")
        print(f"        OST PUBLISHER v{VERSION}       ")
        print("=========================================")
        print("RADAR OPTIONS:")
        print("  1. Preview Radar")
        print("  2. Record Radar")
        print("\nCAMERA OPTIONS:")
        print("  3. Preview Camera (MediaPipe)")
        print("  4. Record Camera (MediaPipe)")
        print("\nSYSTEM:")
        print("  0. Exit")
        
        # Removed the \n inside input() to fix the space+enter glitch
        print("Select an option (0-4):")
        choice = input()
        
        if choice == '1': run_radar_stream(context, record=False)
        elif choice == '2': run_radar_stream(context, record=True)
        elif choice == '3': run_camera_stream(context, record=False)
        elif choice == '4': run_camera_stream(context, record=True)
        elif choice == '0':
            print("Shutting down network and exiting...")
            break
        else: print("Invalid choice.")

    context.term()
    sys.exit(0)

if __name__ == "__main__":
    main()