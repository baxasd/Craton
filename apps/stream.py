import sys
import time
import datetime
import logging
import zmq
import json
import configparser
import cv2

from core.radar.parser import parse_standard_frame
from core.ui.theme import VERSION
from core.io.storage import CameraSessionWriter, RadarSessionWriter

# Set up the console logger so it prints clean, timestamped messages instead of ugly raw text
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Publisher")

# ─────────────────────────────────────────────────────────────────────────────
#  Load Global Settings
# ─────────────────────────────────────────────────────────────────────────────
# We read the central settings.ini file so ports and hardware configs are synced across all apps.
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
    # DEFERRED IMPORT: We only import the hardware driver if the user actually selects Radar.
    from sensors.mmWave import RadarSensor 
    
    log.info("Connecting to Texas Instruments hardware...")
    
    cli, data = None, None
    # Check if the user hardcoded the COM ports in settings.ini, otherwise auto-scan
    if HW_CLI_PORT.lower() != 'auto' and HW_DATA_PORT.lower() != 'auto':
        cli, data = HW_CLI_PORT, HW_DATA_PORT
    else:
        log.info("Scanning for auto-assigned USB ports...")
        cli, data = RadarSensor.find_ti_ports()
    
    if not cli or not data:
        log.error("Auto-detection failed: No TI radar ports found. Please check connections.")
        return None

    log.info(f"Using CLI: {cli} | DATA: {data}")
    
    # Initialize the sensor and upload the configuration profile to the board
    radar = RadarSensor(cli, data, HW_CFG_FILE)
    radar.connect_and_configure()
    
    # Print a nice summary of the radar parameters to the console
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
    """The infinite loop that broadcasts the Radar bytes."""
    radar = connect_radar()
    if radar is None: return

    # ONLY bind the Radar port (5555) if the user selects Radar. This prevents port collisions.
    zmq_socket = zmq_context.socket(zmq.PUB)
    zmq_socket.bind(f"tcp://*:{ZMQ_RADAR_PORT}")

    # If we are in Record mode, initialize the Parquet writer. Otherwise, leave it None.
    writer = RadarSessionWriter(metadata=radar.config.summary()) if record else None
    
    if record: log.info(f"RECORD MODE: Broadcasting over ZMQ and saving to {writer.filepath}")
    else: log.info("PREVIEW MODE: Broadcasting over ZMQ only (No disk writing).")

    print("\n>>> RADAR STREAM ACTIVE. Press Ctrl+C to stop. <<<\n")
    
    try:
        while True:
            # 1. Grab raw bytes from the serial port
            raw_bytes = radar.read_raw_frame()
            if raw_bytes is None:
                # If no data is ready, sleep for 1 millisecond so we don't melt the CPU
                time.sleep(0.001)
                continue

            # 2. Parse the bytes into our standard frame format
            frame = parse_standard_frame(raw_bytes)
            rdhm = frame.get("RDHM") # Extract the Range-Doppler Heatmap matrix
            
            # 3. Network Broadcast and Disk Writing
            if rdhm is not None:
                # Blast the raw bytes over the network for view.py to catch
                zmq_socket.send(rdhm.tobytes())
                # Save to hard drive if recording
                if record: writer.write_frame(rdhm)

    except KeyboardInterrupt:
        # Catches the user pressing Ctrl+C in the terminal
        log.info("Ctrl+C detected. Stopping radar stream...")
    finally:
        # CLEANUP: Crucial to release the COM ports and Network ports so they can be used again!
        radar.close()
        zmq_socket.close() 
        if writer: writer.close()
        time.sleep(0.5)


def run_camera_stream(zmq_context: zmq.Context, record: bool):
    """The infinite loop that captures video, runs AI, and broadcasts over ZeroMQ."""
    log.info("Loading camera AI models...")
    
    # DEFERRED IMPORTS: We only load heavy ML models if the Camera is selected. Saves boot time.
    from sensors.realsense import RealSenseCamera
    from core.cv.depth import get_mean_depth, deproject_pixel_to_point
    from core.cv.pose import PoseEstimator
    
    # Pull settings dynamically from the INI file
    cam_w = int(config.get('Camera', 'width', fallback=640))
    cam_h = int(config.get('Camera', 'height', fallback=480))
    cam_fps = int(config.get('Camera', 'fps', fallback=30))
    model_comp = int(config.get('Camera', 'model_complexity', fallback=1))
    jpeg_qual = int(config.get('Camera', 'jpeg_quality', fallback=80))
    
    # Bind the Camera network port (5556)
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

    # Boot the RealSense physical hardware and the MediaPipe ML Engine
    cam = RealSenseCamera(width=cam_w, height=cam_h, fps=cam_fps)
    pose = PoseEstimator(model_complexity=model_comp)

    print("\n>>> CAMERA STREAM ACTIVE. Press Ctrl+C to stop. <<<\n")
    try:
        while True:
            # 1. Get raw video and depth matrices from the RealSense
            color_img, depth_frame = cam.get_frames()
            if color_img is None:
                continue

            h, w, _ = color_img.shape
            
            # 2. Run the image through MediaPipe to find the 2D skeleton joints
            landmarks = pose.estimate(color_img)
            
            # 3. Create the data dictionary to send over the network
            frame_data = {"timestamp": time.time()}
            depth_intrin = None

            # Get the physical properties of the camera lens (intrinsics) for 3D math
            if depth_frame:
                depth_intrin = depth_frame.profile.as_video_stream_profile().intrinsics

            if landmarks:
                # Loop through all 33 human joints found by the AI
                for i, (lx, ly, lz) in enumerate(landmarks):
                    cx, cy = int(lx), int(ly)
                    if 0 <= cx < w and 0 <= cy < h:
                        # Draw a green dot directly onto the video frame
                        cv2.circle(color_img, (cx, cy), 3, (0, 255, 0), -1)
                        
                        # 4. Math: Convert 2D pixel to 3D physical coordinate in real-world meters
                        if depth_intrin:
                            dist = get_mean_depth(depth_frame, cx, cy, w, h)
                            if dist:
                                p = deproject_pixel_to_point(depth_intrin, cx, cy, dist)
                                frame_data[f"j{i}_x"] = p[0]
                                frame_data[f"j{i}_y"] = p[1]
                                frame_data[f"j{i}_z"] = p[2]

            # 5. Compress the raw image matrix into a tiny JPEG file to save network bandwidth
            ret, jpeg_buffer = cv2.imencode('.jpg', color_img, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_qual])
            
            # 6. Network Broadcast
            if ret:
                # Send a "Multipart" message. Part 1 is the Skeleton JSON, Part 2 is the JPEG image.
                zmq_socket.send_multipart([
                    json.dumps(frame_data).encode('utf-8'),
                    jpeg_buffer.tobytes()
                ])

            # 7. Disk Write
            if record and writer:
                writer.write_frame(frame_data)

    except KeyboardInterrupt:
        log.info("Ctrl+C detected. Stopping camera stream...")
    finally:
        # CLEANUP
        cam.stop()
        zmq_socket.close() 
        if writer: writer.close()

# ─────────────────────────────────────────────────────────────────────────────
#  Main Application Menu
# ─────────────────────────────────────────────────────────────────────────────
def main():
    # The ZeroMQ Context handles threading and network card management under the hood.
    # We create it once here, and pass it to whatever stream the user selects.
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
        
        # Flush the terminal buffer and ask for input
        print("\nSelect an option (0-4): ", end="", flush=True)
        choice = input().strip()
        
        if choice == '1': run_radar_stream(context, record=False)
        elif choice == '2': run_radar_stream(context, record=True)
        elif choice == '3': run_camera_stream(context, record=False)
        elif choice == '4': run_camera_stream(context, record=True)
        elif choice == '0':
            print("Shutting down network and exiting...")
            break
        else: 
            print("Invalid choice.")

    # Gracefully shut down the networking system before closing Python
    context.term()
    sys.exit(0)

if __name__ == "__main__":
    main()