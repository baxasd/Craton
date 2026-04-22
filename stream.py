import sys
import os
import time
import datetime
import logging
import zmq
import json
import configparser
import cv2
import numpy as np
from src.radar.parse import parse_standard_frame
from src.data.store import CameraSessionWriter, RadarSessionWriter
from src.utils.theme import SETTINGS_PATH
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule

# Rich Console
console = Console()

# Setup timestamped console logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Publisher")

if getattr(sys, 'frozen', False):
    os.chdir(sys._MEIPASS)
    
# Load global configuration
config = configparser.ConfigParser(interpolation=None)
config.read(SETTINGS_PATH)

HW_CFG_FILE = config['Hardware']['radar_cfg_file']
HW_CLI_PORT = config['Hardware']['cli_port']
HW_DATA_PORT = config['Hardware']['data_port']
ZMQ_RADAR_PORT = config['Network'].get('zmq_radar_port', '5555')
ZMQ_CAM_PORT = config['Network'].get('zmq_camera_port', '5556')

# Load Curve25519 encryption keys for the server
SERVER_PUBLIC = config['Security']['server_public'].encode('ascii')
SERVER_SECRET = config['Security']['server_secret'].encode('ascii')

def connect_radar():
    """Initialize the TI mmWave radar and upload the hardware profile."""
    from src.hardware.radar import RadarSensor 
    
    log.info("Connecting to Texas Instruments hardware...")
    
    # Auto-detect COM ports if not explicitly defined
    if HW_CLI_PORT.lower() != 'auto' and HW_DATA_PORT.lower() != 'auto':
        cli, data = HW_CLI_PORT, HW_DATA_PORT
    else:
        cli, data = RadarSensor.find_ti_ports()
    
    if not cli or not data:
        log.error("Failed to detect TI radar ports.")
        return None

    log.info(f"Using CLI: {cli} | DATA: {data}")
    
    radar = RadarSensor(cli, data, HW_CFG_FILE)
    radar.connect_and_configure()
    
    print("Radar Configuration Summary:")
    for key, value in radar.config.summary().items():
        print(f" {key:<20}: {value}")
    print("="*40 + "\n")
    
    return radar

def run_radar_stream(zmq_context: zmq.Context, record: bool):
    """Capture raw radar bytes, parse them, and broadcast over encrypted ZMQ."""
    radar = connect_radar()
    if radar is None: return

    # Configure secure PUB socket
    zmq_socket = zmq_context.socket(zmq.PUB)
    zmq_socket.curve_secretkey = SERVER_SECRET
    zmq_socket.curve_publickey = SERVER_PUBLIC
    zmq_socket.curve_server = True
    zmq_socket.bind(f"tcp://*:{ZMQ_RADAR_PORT}")

    # Initialize local storage if recording is enabled
    writer = RadarSessionWriter(metadata=radar.config.summary()) if record else None
    log.info(f"{'RECORD' if record else 'PREVIEW'} MODE: Radar stream active.")

    try:
        while True:
            raw_bytes = radar.read_raw_frame()
            if raw_bytes is None:
                time.sleep(0.001)
                continue

            frame = parse_standard_frame(raw_bytes)
            rdhm = frame.get("RDHM") 
            
            # Broadcast the heatmap matrix
            if rdhm is not None:
                zmq_socket.send(rdhm.tobytes())
                if record: writer.write_frame(rdhm)

    except KeyboardInterrupt:
        log.info("Stopping radar stream...")
    finally:
        # Safely release hardware and network bindings
        radar.close()
        zmq_socket.close() 
        if writer: writer.close()
        time.sleep(0.5)

def run_camera_stream(zmq_context: zmq.Context, record: bool):
    """Capture RealSense video, run MediaPipe pose estimation, and broadcast."""
    log.info("Initializing RealSense and MediaPipe...")
    
    from src.hardware.cam import RealSenseCamera
    from src.vision.depth import get_mean_depth, deproject_pixel_to_point
    from src.vision.pose import PoseEstimator
    
    cam_w = int(config.get('Camera', 'width', fallback=640))
    cam_h = int(config.get('Camera', 'height', fallback=480))
    cam_fps = int(config.get('Camera', 'fps', fallback=30))
    model_comp = int(config.get('Camera', 'model_complexity', fallback=1))
    jpeg_qual = int(config.get('Camera', 'jpeg_quality', fallback=80))
    
    cam = RealSenseCamera(width=cam_w, height=cam_h, fps=cam_fps)
    if cam.pipeline is None:
        log.error("Camera detection failed.")
        return

    pose = PoseEstimator(model_complexity=model_comp)
    
    # Configure secure PUB socket
    zmq_socket = zmq_context.socket(zmq.PUB)
    zmq_socket.curve_secretkey = SERVER_SECRET
    zmq_socket.curve_publickey = SERVER_PUBLIC
    zmq_socket.curve_server = True
    zmq_socket.bind(f"tcp://*:{ZMQ_CAM_PORT}")

    # Initialize local storage if recording is enabled
    writer = None
    if record:
        meta = {"Date": datetime.datetime.now().isoformat()}
        writer = CameraSessionWriter(metadata=meta)
    
    log.info(f"{'RECORD' if record else 'PREVIEW'} MODE: Camera stream active.")

    try:
        while True:
            color_img, depth_frame = cam.get_frames()
            if color_img is None:
                time.sleep(0.01)
                continue

            h, w, _ = color_img.shape
            landmarks = pose.estimate(color_img)
            frame_data = {"timestamp": time.time()}
            ui_data = {}
            
            depth_intrin = depth_frame.profile.as_video_stream_profile().intrinsics if depth_frame else None

            if landmarks:
                for i, (lx, ly, lz) in enumerate(landmarks):
                    cx, cy = int(lx), int(ly)
                    if 0 <= cx < w and 0 <= cy < h:
                        
                        ui_data[f"j{i}_px"] = cx
                        ui_data[f"j{i}_py"] = cy
                        
                        if depth_intrin:
                            dist = get_mean_depth(depth_frame, cx, cy, w, h)
                            if dist:
                                p = deproject_pixel_to_point(depth_intrin, cx, cy, dist)
                                frame_data[f"j{i}_x"], frame_data[f"j{i}_y"], frame_data[f"j{i}_z"] = p

            ret, jpeg_buffer = cv2.imencode('.jpg', color_img, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_qual])
            
            ret_depth = False
            if depth_frame:
                depth_array = np.asanyarray(depth_frame.get_data())
                depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_array, alpha=0.045), cv2.COLORMAP_JET)
                ret_depth, depth_jpeg = cv2.imencode('.jpg', depth_colormap, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_qual])
            
            # Broadcast
            if ret and ret_depth:
                network_payload = {**frame_data, **ui_data}
                
                zmq_socket.send_multipart([
                    json.dumps(network_payload).encode('utf-8'),
                    jpeg_buffer.tobytes(),
                    depth_jpeg.tobytes()
                ])

            if record and writer:
                writer.write_frame(frame_data)

    except KeyboardInterrupt:
        log.info("Stopping camera stream...")
    finally:
        cam.stop()
        zmq_socket.close() 
        if writer: writer.close()
        time.sleep(0.5)

def main():
    """CLI bootstrapper and context manager."""
    context = zmq.Context()

    menu_content = Group(
        Rule("Radar", align="center", style="line"),
        "  [red]1.[/red] Preview Radar",
        "  [red]2.[/red] Record Radar",
        Rule("Camera", align="center", style="line"),
        "  [red]3.[/red] Preview Camera",
        "  [red]4.[/red] Record Camera",
        Rule(align="left", style="line"),
        "  [red]0.[/red] Exit"
    )

    while True:
        console.clear() 
        console.print(Panel(menu_content, title="[bold] Craton Engine [/bold]", expand=False))
        choice = Prompt.ask("\nSelect operation", choices=["0", "1", "2", "3", "4"], default="1")
        
        if choice == '1': 
            run_radar_stream(context, record=False)
        elif choice == '2': 
            run_radar_stream(context, record=True)
        elif choice == '3': 
            run_camera_stream(context, record=False)
        elif choice == '4': 
            run_camera_stream(context, record=True)
        elif choice == '0':
            console.print("[dim]Exiting...[/dim]")
            break

    context.term()
    sys.exit(0)

if __name__ == "__main__":
    main()