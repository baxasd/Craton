import sys
import logging
import os
import zmq
import json
import numpy as np
import scipy.ndimage as ndimage
import pyqtgraph as pg
import configparser
import cv2  # Added for OpenCV rendering
from PIL import Image, ImageDraw, ImageFont

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QLabel
from PyQt6.QtGui import QPixmap, QIcon, QImage # Added QImage

from core.radar.parser import RadarConfig
from core.ui.theme import COLOR_MAIN_BG, COLOR_TEXT, APP_VERSION, ICON_PATH, SETTINGS_PATH

# Setup terminal logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Viewer")

if getattr(sys, 'frozen', False):
    os.chdir(sys._MEIPASS)

# Load global configuration
config = configparser.ConfigParser(interpolation=None)
config.read(SETTINGS_PATH)

HW_CFG_FILE     = config['Hardware']['radar_cfg_file']
ZMQ_RADAR_PORT  = config['Network'].get('zmq_radar_port', '5555')
ZMQ_CAM_PORT    = config['Network'].get('zmq_camera_port', '5556')

VIEW_IP         = config['Viewer']['default_ip']
MAX_RANGE       = float(config['Viewer']['max_range_m'])
CMAP            = config['Viewer']['cmap']
DISP_LOW_PCT    = float(config['Viewer']['low_pct'])
DISP_HIGH_PCT   = float(config['Viewer']['high_pct'])
SMOOTH_GRID     = int(config['Viewer']['smooth_grid_size'])

# Load Curve25519 encryption keys for the client
SERVER_PUBLIC = config['Security']['server_public'].encode('ascii')
CLIENT_PUBLIC = config['Security']['client_public'].encode('ascii')
CLIENT_SECRET = config['Security']['client_secret'].encode('ascii')

class ZmqRadarWorker(QThread):
    """Background thread for receiving and processing encrypted radar matrices."""
    new_frame = pyqtSignal(np.ndarray, float, float) 
    error     = pyqtSignal(str)

    def __init__(self, cfg: RadarConfig, publisher_ip: str, zoom_y: float, zoom_x: float):
        super().__init__()
        self.cfg = cfg
        self.running = True
        self.zoom_y = zoom_y
        self.zoom_x = zoom_x
        
        self.num_range_bins = cfg.numRangeBins
        self.num_vel_bins   = cfg.numLoops
        self.max_bin = min(int(MAX_RANGE / cfg.rangeRes), cfg.numRangeBins)
        self._expected_size = self.num_range_bins * self.num_vel_bins

        # Configure secure SUB socket
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.curve_secretkey = CLIENT_SECRET
        self.socket.curve_publickey = CLIENT_PUBLIC
        self.socket.curve_serverkey = SERVER_PUBLIC

        self.socket.connect(f"tcp://{publisher_ip}:{ZMQ_RADAR_PORT}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

    def run(self):
        while self.running:
            try:
                if self.socket.poll(100) == 0:
                    continue 

                msg = self.socket.recv(flags=zmq.NOBLOCK)
                raw = np.frombuffer(msg, dtype=np.uint16)
                
                if raw.size != self._expected_size: continue

                # Calculate radar heatmap (dB) and upsample for rendering
                rd = raw.astype(np.float32).reshape(self.num_range_bins, self.num_vel_bins)
                rd = rd[:self.max_bin, :]
                display = 20.0 * np.log10(np.abs(np.fft.fftshift(rd, axes=1)) + 1e-6)
                smooth = ndimage.zoom(display, (self.zoom_y, self.zoom_x), order=1)
                
                # Dynamic contrast scaling
                lo = float(np.percentile(smooth, DISP_LOW_PCT))
                hi = float(np.percentile(smooth, DISP_HIGH_PCT))
                if lo >= hi: hi = lo + 0.1

                self.new_frame.emit(smooth, lo, hi)
                
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        self.running = False
        self.wait()
        self.socket.close()
        self.context.term()

class ZmqCameraWorker(QThread):
    """Background thread for receiving and decoding encrypted camera JSON and JPEGs."""
    new_frame = pyqtSignal(dict, bytes)
    error     = pyqtSignal(str)

    def __init__(self, publisher_ip: str):
        super().__init__()
        self.running = True
        
        # Configure secure SUB socket
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.curve_secretkey = CLIENT_SECRET
        self.socket.curve_publickey = CLIENT_PUBLIC
        self.socket.curve_serverkey = SERVER_PUBLIC

        self.socket.connect(f"tcp://{publisher_ip}:{ZMQ_CAM_PORT}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

    def run(self):
        while self.running:
            try:
                if self.socket.poll(100) == 0:
                    continue

                msg_parts = self.socket.recv_multipart(flags=zmq.NOBLOCK)
                if len(msg_parts) == 2:
                    meta_dict = json.loads(msg_parts[0].decode('utf-8'))
                    img_bytes = msg_parts[1]
                    self.new_frame.emit(meta_dict, img_bytes)
                    
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        self.running = False
        self.wait()
        self.socket.close()
        self.context.term()

class LiveViewerWindow(QMainWindow):
    """Main PyQt6 UI for visualizing telemetry."""
    def __init__(self, cfg: RadarConfig, publisher_ip: str):
        super().__init__()
        self.cfg = cfg
        self.publisher_ip = publisher_ip
        
        self.zoom_y = 1.0
        self.zoom_x = 1.0

        self.setWindowTitle(f"OST Live Telemetry | {self.publisher_ip} (Encrypted)")
        self.setFixedSize(1400, 720) # Made bigger for the showcase
        self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {COLOR_MAIN_BG}; }}
            #CamFeed {{ background-color: transparent; border: none; }}
        """)

        # Cache physical bounds for the radar axes
        self.max_range_val = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins) * self.cfg.rangeRes
        self.dop_max = self.cfg.dopMax
        
        self._precompute_zoom() 
        self._build_ui()
        self._start_workers()

    def _precompute_zoom(self):
        """Calculate interpolation factors to match the target smooth grid."""
        src_rows = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins)
        src_cols = self.cfg.numLoops
        self.zoom_y = max(SMOOTH_GRID, src_rows) / src_rows
        self.zoom_x = max(SMOOTH_GRID, src_cols) / src_cols

    def _build_ui(self):
        """Construct the horizontal dual-panel layout."""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10) 
        main_layout.setSpacing(10) 
        
        # Radar Panel
        self.plot_radar = pg.PlotWidget()
        self.plot_radar.setBackground(COLOR_MAIN_BG)
        self.plot_radar.setTitle(None)
        
        # Format axes
        styles = {'color': COLOR_TEXT, 'font-size': '12px', 'font-family': 'Segoe UI'}
        self.plot_radar.setLabel("left", "Range", units="m", **styles)
        self.plot_radar.setLabel("bottom", "Velocity", units="m/s", **styles)
        self.plot_radar.getPlotItem().hideAxis('top')
        self.plot_radar.getPlotItem().hideAxis('right')
        
        pen = pg.mkPen(color=COLOR_TEXT, width=1)
        self.plot_radar.getAxis('left').setPen(pen)
        self.plot_radar.getAxis('left').setTextPen(COLOR_TEXT)
        self.plot_radar.getAxis('bottom').setPen(pen)
        self.plot_radar.getAxis('bottom').setTextPen(COLOR_TEXT)
        self.plot_radar.showGrid(x=True, y=True, alpha=0.2) 
        
        self.img_radar = pg.ImageItem()
        self.img_radar.setColorMap(pg.colormap.get(CMAP))
        self.plot_radar.addItem(self.img_radar)
        
        self.plot_radar.setXRange(-self.dop_max, self.dop_max, padding=0)
        self.plot_radar.setYRange(0, self.max_range_val, padding=0)
        main_layout.addWidget(self.plot_radar, stretch=1)

        # Camera Panel
        self.lbl_cam_feed = QLabel()
        self.lbl_cam_feed.setObjectName("CamFeed") 
        self.lbl_cam_feed.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        main_layout.addWidget(self.lbl_cam_feed, stretch=2)

    def _start_workers(self):
        """Boot background networking threads."""
        self.w_radar = ZmqRadarWorker(self.cfg, self.publisher_ip, self.zoom_y, self.zoom_x)
        self.w_radar.new_frame.connect(self._on_radar_frame)
        self.w_radar.start()

        self.w_cam = ZmqCameraWorker(self.publisher_ip)
        self.w_cam.new_frame.connect(self._on_cam_frame)
        self.w_cam.start()

    def _on_radar_frame(self, smooth_matrix: np.ndarray, lo: float, hi: float):
        """Render radar frame and enforce axis alignment bounds."""
        self.img_radar.setImage(smooth_matrix, autoLevels=False, levels=(lo, hi))
        align_rect = pg.QtCore.QRectF(
            -self.dop_max, 0, self.dop_max * 2.0, self.max_range_val
        )
        self.img_radar.setRect(align_rect)

    def _draw_showcase_overlay(self, frame, meta: dict):
        """Draws the full MediaPipe skeleton and a compact HD Telemetry Sidebar."""
        
        conns = [
            (0,1), (1,2), (2,3), (3,7), (0,4), (4,5), (5,6), (6,8), (9,10), # Face
            (11,12), (11,13), (13,15), (15,17), (15,19), (15,21), (17,19),  # Left Arm/Hand
            (12,14), (14,16), (16,18), (16,20), (16,22), (18,20),           # Right Arm/Hand
            (11,23), (12,24), (23,24),                                      # Torso
            (23,25), (25,27), (27,29), (29,31), (31,27),                    # Left Leg/Foot
            (24,26), (26,28), (28,30), (30,32), (32,28)                     # Right Leg/Foot
        ]
        
        angles_to_track = {
            'L_Knee': (23, 25, 27), 'R_Knee': (24, 26, 28),
            'L_Elbow': (11, 13, 15), 'R_Elbow': (12, 14, 16)
        }

        # OpenCV BGR Colors for shapes
        CV_LEFT = (0, 165, 255)     
        CV_RIGHT = (255, 130, 0)    
        CV_CENTER = (255, 255, 255) 

        # 1. Draw Skeleton Lines (Underneath)
        for p1, p2 in conns:
            if f"j{p1}_px" in meta and f"j{p2}_px" in meta:
                pt1 = (int(meta[f"j{p1}_px"]), int(meta[f"j{p1}_py"]))
                pt2 = (int(meta[f"j{p2}_px"]), int(meta[f"j{p2}_py"]))
                cv2.line(frame, pt1, pt2, (220, 220, 220), 2, cv2.LINE_AA)

        # 2. Draw Side-Coded Joints (On Top)
        for i in range(33):
            if f"j{i}_px" in meta and f"j{i}_py" in meta:
                cx, cy = int(meta[f"j{i}_px"]), int(meta[f"j{i}_py"])
                
                if i == 0: dot_color = CV_CENTER
                elif i % 2 != 0: dot_color = CV_LEFT
                else: dot_color = CV_RIGHT
                
                cv2.circle(frame, (cx, cy), 5, (255, 255, 255), 2, cv2.LINE_AA) 
                cv2.circle(frame, (cx, cy), 4, dot_color, -1, cv2.LINE_AA)      

        # 3. Compact HUD Sidebar Background Panel
        overlay = frame.copy()
        # Shrunk the box to be much tighter around the text
        cv2.rectangle(overlay, (10, 10), (130, 200), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 1, frame, 0.2, 0, frame)

        # ==========================================
        # 4. HD TEXT RENDERING (Pillow)
        # ==========================================
        
        # Convert OpenCV's BGR image to RGB for Pillow
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(pil_img)

        # Slightly smaller fonts for the compact layout
        try:
            font_title = ImageFont.truetype("roboto.ttf", 12)
            font_body = ImageFont.truetype("roboto.ttf", 10)
        except IOError:
            font_title = ImageFont.load_default()
            font_body = ImageFont.load_default()

        # Brightened RGB Colors for contrast against the black box
        RGB_LEFT = (255, 180, 50)      # Bright Orange
        RGB_RIGHT = (100, 200, 255)    # Light Sky Blue

        # Draw Header (Removed Stroke)
        draw.text((15, 15), "Metrics", font=font_title, fill=(255, 255, 255))

        y_offset = 30
        for name, (i1, i2, i3) in angles_to_track.items():
            if all(f"j{i}_x" in meta for i in [i1, i2, i3]):
                
                # Biomechanical Math
                v1 = np.array([meta[f"j{i1}_x"], meta[f"j{i1}_y"], meta[f"j{i1}_z"]])
                v2 = np.array([meta[f"j{i2}_x"], meta[f"j{i2}_y"], meta[f"j{i2}_z"]])
                v3 = np.array([meta[f"j{i3}_x"], meta[f"j{i3}_y"], meta[f"j{i3}_z"]])
                
                ba, bc = v1 - v2, v3 - v2
                n_ba, n_bc = np.linalg.norm(ba), np.linalg.norm(bc)
                
                if n_ba == 0 or n_bc == 0: continue
                    
                cosine = np.dot(ba, bc) / (n_ba * n_bc)
                deg = int(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
                
                text_color = RGB_LEFT if "L_" in name else RGB_RIGHT
                display_name = name.replace("_", " ").upper()
                
                # Draw Crisp Data text (Removed Stroke, tightened y_offset)
                draw.text((15, y_offset), f"{display_name}: {deg}\u00B0", font=font_body, fill=text_color)
                y_offset += 15

        # Convert back to OpenCV format so PyQt can display it
        frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return frame

    def _on_cam_frame(self, meta: dict, img_bytes: bytes):
        """Decode JPEG payload, draw overlay, and update UI Pixmap."""
        # 1. Decode raw bytes into OpenCV Image
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        # 2. Draw the skeleton using the pixel coordinates from the JSON
        frame = self._draw_showcase_overlay(frame, meta)

        # 3. Convert OpenCV BGR back to PyQt RGB format
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_h, img_w, ch = rgb.shape
        bytes_per_line = ch * img_w
        
        qt_img = QImage(rgb.data, img_w, img_h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        
        # 4. Scale and set
        lbl_w = self.lbl_cam_feed.width()
        lbl_h = self.lbl_cam_feed.height()
        if lbl_w > 0 and lbl_h > 0:
            self.lbl_cam_feed.setPixmap(pixmap.scaled(lbl_w, lbl_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def closeEvent(self, event):
        """Terminate networking safely before UI closes."""
        log.info("Shutting Down...")
        self.w_radar.stop()
        self.w_cam.stop()
        event.accept()

def main():
    print("\n*******************************")
    print(f"****** OST VIEWER {APP_VERSION} ******")
    print("*******************************")
    ip_input = input(f"\nEnter Stream IP. Leave blank for localhost: ").strip()
    ip = VIEW_IP if not ip_input else ip_input
            
    app = QApplication.instance() or QApplication(sys.argv)
    pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)
    
    try:
        cfg = RadarConfig(HW_CFG_FILE)
        window = LiveViewerWindow(cfg, ip)
        window.show()
        app.exec()
    except Exception as e:
        log.error(f"Failed to initialize: {e}")

if __name__ == "__main__":
    main()