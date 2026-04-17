import sys
import logging
import os
import zmq
import json
import numpy as np
import scipy.ndimage as ndimage
import pyqtgraph as pg
import configparser
import cv2  
from rich.console import Console
from rich.prompt import Prompt
import time
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy)
from PyQt6.QtGui import QPixmap, QIcon, QImage, QFont
from core.radar.parser import RadarConfig
from core.ui.theme import ICON_PATH, SETTINGS_PATH

# Initialize console globally (or at the top of your file)
console = Console()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Viewer")

if getattr(sys, 'frozen', False):
    os.chdir(sys._MEIPASS)

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

# Load Curve25519 encryption keys
SERVER_PUBLIC = config['Security']['server_public'].encode('ascii')
CLIENT_PUBLIC = config['Security']['client_public'].encode('ascii')
CLIENT_SECRET = config['Security']['client_secret'].encode('ascii')

COLOR_MAIN_BG = "#FFFFFF"
COLOR_TEXT = "#333333"

class ZmqRadarWorker(QThread):
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
                if self.socket.poll(100) == 0: continue 

                msg = self.socket.recv(flags=zmq.NOBLOCK)
                raw = np.frombuffer(msg, dtype=np.uint16)
                
                if raw.size != self._expected_size: continue

                rd = raw.astype(np.float32).reshape(self.num_range_bins, self.num_vel_bins)
                rd = rd[:self.max_bin, :]
                display = 20.0 * np.log10(np.abs(np.fft.fftshift(rd, axes=1)) + 1e-6)
                smooth = ndimage.zoom(display, (self.zoom_y, self.zoom_x), order=1)
                
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
    new_frame = pyqtSignal(dict, bytes, bytes)
    error     = pyqtSignal(str)

    def __init__(self, publisher_ip: str):
        super().__init__()
        self.running = True
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
                if self.socket.poll(100) == 0: continue

                msg_parts = self.socket.recv_multipart(flags=zmq.NOBLOCK)
                if len(msg_parts) >= 2:
                    meta_dict = json.loads(msg_parts[0].decode('utf-8'))
                    img_bytes = msg_parts[1]
                    depth_bytes = msg_parts[2] if len(msg_parts) == 3 else b'' 
                    self.new_frame.emit(meta_dict, img_bytes, depth_bytes)
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        self.running = False
        self.wait()
        self.socket.close()
        self.context.term()

class LiveViewerWindow(QMainWindow):
    def __init__(self, cfg: RadarConfig, publisher_ip: str):
        super().__init__()
        self.cfg = cfg
        self.publisher_ip = publisher_ip
        
        self.zoom_y = 1.0
        self.zoom_x = 1.0

        self.setWindowTitle(f"Craton Vision - {self.publisher_ip}")
        self.resize(1100, 750) 
        self.setMinimumSize(800, 500)
        self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {COLOR_MAIN_BG}; }}
            QLabel {{ color: {COLOR_TEXT}; }}
            .PanelHeader {{ font-weight: 800; font-size: 11px; color: #888; padding-bottom: 2px; }}
            #KinematicsBar {{ background-color: #F4F5F7; border-radius: 4px; border: 1px solid #EAEAEA; }}
            #FeedContainer {{ background-color: #000000; border-radius: 4px; }}
        """)

        self.max_range_val = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins) * self.cfg.rangeRes
        self.dop_max = self.cfg.dopMax
        
        self._precompute_zoom() 
        self._build_ui()
        self._start_workers()

    def _precompute_zoom(self):
        src_rows = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins)
        src_cols = self.cfg.numLoops
        self.zoom_y = max(SMOOTH_GRID, src_rows) / src_rows
        self.zoom_x = max(SMOOTH_GRID, src_cols) / src_cols

    def _create_header(self, title):
        lbl = QLabel(title.upper())
        lbl.setProperty("class", "PanelHeader")
        return lbl

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16) 
        main_layout.setSpacing(16) 

        # RADAR
        radar_panel = QVBoxLayout()
        radar_panel.setContentsMargins(0, 0, 0, 0)
        radar_panel.setSpacing(5)
        
        radar_panel.addWidget(self._create_header("mmWave Radar"))

        self.plot_radar = pg.PlotWidget()
        self.plot_radar.setBackground(COLOR_MAIN_BG)
        self.plot_radar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        styles = {'color': COLOR_TEXT, 'font-size': '11px', 'font-family': 'Inter'}
        self.plot_radar.setLabel("left", "Range", units="m", **styles)
        self.plot_radar.setLabel("bottom", "Velocity", units="m/s", **styles)
        self.plot_radar.getPlotItem().hideAxis('top')
        self.plot_radar.getPlotItem().hideAxis('right')
        
        pen = pg.mkPen(color=COLOR_TEXT, width=1)
        tick_font = QFont("Inter", 9, QFont.Weight.Medium)
        
        self.plot_radar.getAxis('left').setPen(pen)
        self.plot_radar.getAxis('left').setTextPen(COLOR_TEXT)
        self.plot_radar.getAxis('left').setTickFont(tick_font)
        
        self.plot_radar.getAxis('bottom').setPen(pen)
        self.plot_radar.getAxis('bottom').setTextPen(COLOR_TEXT)
        self.plot_radar.getAxis('bottom').setTickFont(tick_font)
        
        self.plot_radar.showGrid(x=True, y=True, alpha=0.1) 
        
        self.img_radar = pg.ImageItem()
        self.img_radar.setColorMap(pg.colormap.get(CMAP))
        self.plot_radar.addItem(self.img_radar)
        self.plot_radar.setXRange(-self.dop_max, self.dop_max, padding=0)
        self.plot_radar.setYRange(0, self.max_range_val, padding=0)

        radar_panel.addWidget(self.plot_radar)
        main_layout.addLayout(radar_panel, stretch=1) 

        # CAMERA & METRICS
        media_panel = QVBoxLayout()
        media_panel.setContentsMargins(0, 0, 0, 0)
        media_panel.setSpacing(4)

        # Camera RGB
        media_panel.addWidget(self._create_header("Camera RGB"))
        
        self.lbl_cam_feed = QLabel()
        self.lbl_cam_feed.setObjectName("FeedContainer")
        self.lbl_cam_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cam_feed.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        media_panel.addWidget(self.lbl_cam_feed, stretch=1)

        # Metrics Bar
        kinematics_bar = QFrame()
        kinematics_bar.setObjectName("KinematicsBar")
        k_layout = QHBoxLayout(kinematics_bar)
        k_layout.setContentsMargins(12, 6, 12, 6)
        
        lbl_style = "font-size: 11px; color: #555; text-transform: uppercase;"
        val_style = "font-size: 12px; font-weight: 700; color: #111;"

        self.val_l_elbow = QLabel("--°")
        self.val_r_elbow = QLabel("--°")
        self.val_l_knee = QLabel("--°")
        self.val_r_knee = QLabel("--°")

        def add_metric(name, val_label):
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(lbl_style)
            val_label.setStyleSheet(val_style)
            k_layout.addWidget(name_lbl)
            k_layout.addWidget(val_label)
            k_layout.addSpacing(10)

        add_metric("L-Elbow:", self.val_l_elbow)
        add_metric("R-Elbow:", self.val_r_elbow)
        add_metric("L-Knee:", self.val_l_knee)
        add_metric("R-Knee:", self.val_r_knee)
        k_layout.addStretch()

        media_panel.addWidget(kinematics_bar)
        media_panel.addSpacing(12)

        # Depth Map
        media_panel.addWidget(self._create_header("Depth Map"))
        
        self.lbl_depth_feed = QLabel()
        self.lbl_depth_feed.setObjectName("FeedContainer")
        self.lbl_depth_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_depth_feed.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        media_panel.addWidget(self.lbl_depth_feed, stretch=1)

        main_layout.addLayout(media_panel, stretch=1)

    def _start_workers(self):
        self.w_radar = ZmqRadarWorker(self.cfg, self.publisher_ip, self.zoom_y, self.zoom_x)
        self.w_radar.new_frame.connect(self._on_radar_frame)
        self.w_radar.start()

        self.w_cam = ZmqCameraWorker(self.publisher_ip)
        self.w_cam.new_frame.connect(self._on_cam_frame)
        self.w_cam.start()

    def _on_radar_frame(self, smooth_matrix: np.ndarray, lo: float, hi: float):
        self.img_radar.setImage(smooth_matrix, autoLevels=False, levels=(lo, hi))
        align_rect = pg.QtCore.QRectF(-self.dop_max, 0, self.dop_max * 2.0, self.max_range_val)
        self.img_radar.setRect(align_rect)

    def _draw_clean_skeleton(self, frame, meta: dict):
        conns = [
            (0,1), (1,2), (2,3), (3,7), (0,4), (4,5), (5,6), (6,8), (9,10), 
            (11,12), (11,13), (13,15), (15,17), (15,19), (15,21), (17,19),  
            (12,14), (14,16), (16,18), (16,20), (16,22), (18,20),           
            (11,23), (12,24), (23,24),                                      
            (23,25), (25,27), (27,29), (29,31), (31,27),                    
            (24,26), (26,28), (28,30), (30,32), (32,28)                     
        ]

        CV_LEFT = (0, 165, 255)     
        CV_RIGHT = (255, 130, 0)    
        CV_CENTER = (255, 255, 255) 

        for p1, p2 in conns:
            if f"j{p1}_px" in meta and f"j{p2}_px" in meta:
                pt1 = (int(meta[f"j{p1}_px"]), int(meta[f"j{p1}_py"]))
                pt2 = (int(meta[f"j{p2}_px"]), int(meta[f"j{p2}_py"]))
                cv2.line(frame, pt1, pt2, (220, 220, 220), 5, cv2.LINE_AA)

        for i in range(33):
            if f"j{i}_px" in meta and f"j{i}_py" in meta:
                cx, cy = int(meta[f"j{i}_px"]), int(meta[f"j{i}_py"])
                
                if i == 0: dot_color = CV_CENTER
                elif i % 2 != 0: dot_color = CV_LEFT
                else: dot_color = CV_RIGHT
                
                cv2.circle(frame, (cx, cy), 5, (255, 255, 255), 2, cv2.LINE_AA) 
                cv2.circle(frame, (cx, cy), 4, dot_color, -1, cv2.LINE_AA)      

        return frame

    def _update_ui_metrics(self, meta: dict):
        angles_to_track = {
            'L_Knee': (23, 25, 27), 'R_Knee': (24, 26, 28),
            'L_Elbow': (11, 13, 15), 'R_Elbow': (12, 14, 16)
        }

        for name, (i1, i2, i3) in angles_to_track.items():
            if all(f"j{i}_x" in meta for i in [i1, i2, i3]):
                v1 = np.array([meta[f"j{i1}_x"], meta[f"j{i1}_y"], meta[f"j{i1}_z"]])
                v2 = np.array([meta[f"j{i2}_x"], meta[f"j{i2}_y"], meta[f"j{i2}_z"]])
                v3 = np.array([meta[f"j{i3}_x"], meta[f"j{i3}_y"], meta[f"j{i3}_z"]])
                
                ba, bc = v1 - v2, v3 - v2
                n_ba, n_bc = np.linalg.norm(ba), np.linalg.norm(bc)
                
                if n_ba == 0 or n_bc == 0: continue
                    
                cosine = np.dot(ba, bc) / (n_ba * n_bc)
                deg = int(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
                
                if name == 'L_Elbow': self.val_l_elbow.setText(f"{deg}°")
                elif name == 'R_Elbow': self.val_r_elbow.setText(f"{deg}°")
                elif name == 'L_Knee': self.val_l_knee.setText(f"{deg}°")
                elif name == 'R_Knee': self.val_r_knee.setText(f"{deg}°")

    def _on_cam_frame(self, meta: dict, img_bytes: bytes, depth_bytes: bytes):
        if img_bytes:
            self._update_ui_metrics(meta)

            np_arr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            frame = self._draw_clean_skeleton(frame, meta)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img_h, img_w, ch = rgb.shape
            bytes_per_line = ch * img_w
            
            qt_img = QImage(rgb.data, img_w, img_h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qt_img)
            
            self.lbl_cam_feed.setPixmap(pixmap.scaled(self.lbl_cam_feed.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        if depth_bytes:
            depth_arr = np.frombuffer(depth_bytes, np.uint8)
            depth_frame = cv2.imdecode(depth_arr, cv2.IMREAD_COLOR)

            depth_rgb = cv2.cvtColor(depth_frame, cv2.COLOR_BGR2RGB)
            d_h, d_w, d_ch = depth_rgb.shape
            d_bytes_per_line = d_ch * d_w
            
            qt_depth_img = QImage(depth_rgb.data, d_w, d_h, d_bytes_per_line, QImage.Format.Format_RGB888).copy()
            depth_pixmap = QPixmap.fromImage(qt_depth_img)
            
            self.lbl_depth_feed.setPixmap(depth_pixmap.scaled(self.lbl_depth_feed.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def closeEvent(self, event):
        self.w_radar.stop()
        self.w_cam.stop()
        event.accept()

def main():
    console.print(f"\n[bold]Craton Vision[/bold]\n") 
    ip = Prompt.ask("Enter Stream IP", default=VIEW_IP).strip()
            
    app = QApplication.instance() or QApplication(sys.argv)

    global_font = QFont("Inter")
    global_font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(global_font)

    pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)
    
    try:
        with console.status("[dim]Initializing engine and connecting to streams...[/dim]", spinner="dots"):
            time.sleep(3)
            cfg = RadarConfig(HW_CFG_FILE)
            window = LiveViewerWindow(cfg, ip)
        console.print("[green]✔[/green] [dim]Engine active. Launching interface...[/dim]\n")
        
        window.show()
        app.exec()
    except Exception as e:
        console.print(f"\n[bold red]Fatal Error:[/bold red] {e}")
        log.error(f"Failed to initialize: {e}")

if __name__ == "__main__":
    main()