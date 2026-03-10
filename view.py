import sys
import time
import logging
import zmq
import json
import numpy as np
import scipy.ndimage as ndimage
import pyqtgraph as pg
import configparser

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QLabel, QStackedWidget, QSplitter)
from PyQt6.QtGui import QFont, QPixmap

from core.radar.base import RadarConfig
from core.config import * 
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Subscriber")

# ── Load Settings ─────────────────────────────────────────────────────────────
config = configparser.ConfigParser()
config.read('settings.ini')

HW_CFG_FILE     = config['Hardware']['radar_cfg_file']
ZMQ_RADAR_PORT  = config['Network'].get('zmq_port', '5555')
ZMQ_CAM_PORT    = config['Network'].get('zmq_camera_port', '5556')

VIEW_IP         = config['Viewer']['default_ip']
MAX_RANGE       = float(config['Viewer']['max_range_m'])
CMAP            = config['Viewer']['cmap']
DISP_LOW_PCT    = float(config['Viewer']['low_pct'])
DISP_HIGH_PCT   = float(config['Viewer']['high_pct'])
SMOOTH_GRID     = int(config['Viewer']['smooth_grid_size'])

# ─────────────────────────────────────────────────────────────────────────────
#  Background Network Threads
# ─────────────────────────────────────────────────────────────────────────────
class ZmqRadarWorker(QThread):
    new_frame = pyqtSignal(np.ndarray)
    error     = pyqtSignal(str)

    def __init__(self, cfg: RadarConfig, publisher_ip: str):
        super().__init__()
        self.cfg = cfg
        self.running = True
        self.num_range_bins = cfg.numRangeBins
        self.num_vel_bins   = cfg.numLoops
        self.max_bin = min(int(MAX_RANGE / cfg.rangeRes), cfg.numRangeBins)
        self._expected_size = self.num_range_bins * self.num_vel_bins

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(f"tcp://{publisher_ip}:{ZMQ_RADAR_PORT}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

    def run(self):
        while self.running:
            try:
                try:
                    msg = self.socket.recv(flags=zmq.NOBLOCK)
                except zmq.Again:
                    time.sleep(0.001)
                    continue

                raw = np.frombuffer(msg, dtype=np.uint16)
                if raw.size != self._expected_size: continue

                rd = raw.astype(np.float32).reshape(self.num_range_bins, self.num_vel_bins)
                rd = rd[:self.max_bin, :]

                display = 20.0 * np.log10(np.abs(np.fft.fftshift(rd, axes=1)) + 1e-6)
                self.new_frame.emit(display)
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        self.running = False
        self.wait()
        self.socket.close()
        self.context.term()


class ZmqCameraWorker(QThread):
    new_frame = pyqtSignal(dict, bytes) # Emit JSON metadata AND Image Bytes
    error     = pyqtSignal(str)

    def __init__(self, publisher_ip: str):
        super().__init__()
        self.running = True
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(f"tcp://{publisher_ip}:{ZMQ_CAM_PORT}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

    def run(self):
        while self.running:
            try:
                try:
                    msg_parts = self.socket.recv_multipart(flags=zmq.NOBLOCK)
                    # Unpack the multipart payload
                    if len(msg_parts) == 2:
                        meta_dict = json.loads(msg_parts[0].decode('utf-8'))
                        img_bytes = msg_parts[1]
                        self.new_frame.emit(meta_dict, img_bytes)
                except zmq.Again:
                    time.sleep(0.001)
                    continue
            except Exception as e:
                self.error.emit(str(e))
                time.sleep(0.1)

    def stop(self):
        self.running = False
        self.wait()
        self.socket.close()
        self.context.term()

# ─────────────────────────────────────────────────────────────────────────────
#  Main Window UI
# ─────────────────────────────────────────────────────────────────────────────
class LiveViewerWindow(QMainWindow):
    def __init__(self, cfg: RadarConfig, publisher_ip: str):
        super().__init__()
        self.cfg = cfg
        self.publisher_ip = publisher_ip
        
        self.radar_active = False
        self.cam_active = False

        self.setWindowTitle(f"OST Live Telemetry | Connected to: {self.publisher_ip}")
        self.resize(1400, 700)
        self.setStyleSheet(CSS_MAIN_WINDOW)

        self._build_ui()
        self._precompute_zoom()
        self._start_workers()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ── 1. Radar Stack ──
        self.radar_stack = QStackedWidget()
        
        self.lbl_wait_radar = QLabel(f"Waiting for Radar Stream...\n(Listening on Port {ZMQ_RADAR_PORT})")
        self.lbl_wait_radar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_wait_radar.setFont(QFont("Segoe UI", 12))
        self.lbl_wait_radar.setStyleSheet(f"color: {TEXT_DIM}; background-color: {BG_PANEL}; border-radius: 8px;")
        
        self.plot_radar = pg.PlotWidget(title="Live Micro-Doppler Heatmap")
        self.plot_radar.setLabel("left", "Range", units="m", color=TEXT_DIM)
        self.plot_radar.setLabel("bottom", "Velocity", units="m/s", color=TEXT_DIM)
        self.plot_radar.showGrid(x=True, y=True, alpha=0.3)
        self.plot_radar.setBackground(BG_PANEL)
        self.plot_radar.addItem(pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(TEXT_DIM, style=Qt.PenStyle.DashLine, width=1)))

        self.img_radar = pg.ImageItem()
        self.img_radar.setColorMap(pg.colormap.get(CMAP))
        self.plot_radar.addItem(self.img_radar)

        max_bin = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins)
        self._rect = pg.QtCore.QRectF(-self.cfg.dopMax - self.cfg.dopRes / 2.0, 0, self.cfg.dopMax * 2.0, max_bin * self.cfg.rangeRes)
        self.img_radar.setRect(self._rect)

        self.radar_stack.addWidget(self.lbl_wait_radar)
        self.radar_stack.addWidget(self.plot_radar)
        splitter.addWidget(self.radar_stack)

        # ── 2. Camera Stack ──
        self.cam_stack = QStackedWidget()
        
        self.lbl_wait_cam = QLabel(f"Waiting for Camera Video Stream...\n(Listening on Port {ZMQ_CAM_PORT})")
        self.lbl_wait_cam.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_wait_cam.setFont(QFont("Segoe UI", 12))
        self.lbl_wait_cam.setStyleSheet(f"color: {TEXT_DIM}; background-color: {BG_PANEL}; border-radius: 8px;")
        
        # Native Video rendering frame
        self.lbl_cam_feed = QLabel()
        self.lbl_cam_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cam_feed.setStyleSheet(f"background-color: {BG_PANEL}; border-radius: 8px;")
        
        self.cam_stack.addWidget(self.lbl_wait_cam)
        self.cam_stack.addWidget(self.lbl_cam_feed)
        splitter.addWidget(self.cam_stack)

        main_layout.addWidget(splitter)

    def _precompute_zoom(self):
        src_rows = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins)
        src_cols = self.cfg.numLoops
        self._zoom_y = max(SMOOTH_GRID, src_rows) / src_rows
        self._zoom_x = max(SMOOTH_GRID, src_cols) / src_cols

    def _start_workers(self):
        self.w_radar = ZmqRadarWorker(self.cfg, self.publisher_ip)
        self.w_radar.new_frame.connect(self._on_radar_frame)
        self.w_radar.start()

        self.w_cam = ZmqCameraWorker(self.publisher_ip)
        self.w_cam.new_frame.connect(self._on_cam_frame)
        self.w_cam.start()

    def _on_radar_frame(self, matrix: np.ndarray):
        if not self.radar_active:
            self.radar_stack.setCurrentIndex(1)
            self.radar_active = True

        smooth = ndimage.zoom(matrix, (self._zoom_y, self._zoom_x), order=1)
        lo = float(np.percentile(smooth, DISP_LOW_PCT))
        hi = float(np.percentile(smooth, DISP_HIGH_PCT))
        if lo >= hi: hi = lo + 0.1

        self.img_radar.setImage(smooth, autoLevels=False, levels=(lo, hi))

    def _on_cam_frame(self, meta: dict, img_bytes: bytes):
        if not self.cam_active:
            self.cam_stack.setCurrentIndex(1)
            self.cam_active = True

        # Decode the JPEG bytes perfectly back into an image
        pixmap = QPixmap()
        pixmap.loadFromData(img_bytes)
        
        # Scale to fit the dynamic UI window size while preserving 4:3 ratio
        lbl_w = self.lbl_cam_feed.width()
        lbl_h = self.lbl_cam_feed.height()
        if lbl_w > 0 and lbl_h > 0:
            self.lbl_cam_feed.setPixmap(pixmap.scaled(lbl_w, lbl_h, Qt.AspectRatioMode.KeepAspectRatio))

    def closeEvent(self, event):
        log.info("Closing viewer and safely killing ZMQ connections...")
        self.w_radar.stop()
        self.w_cam.stop()
        event.accept()

# ─────────────────────────────────────────────────────────────────────────────
#  Application Menu
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=========================================")
    print("        OST LIVE TELEMETRY VIEWER       ")
    print("=========================================")

    while True:
        print("\nCONNECTION MENU:")
        print(f"  1. Connect to Localhost ({VIEW_IP})")
        print("  2. Connect to External IP")
        print("  3. Exit")
        
        choice = input("\nSelect an option (1-3): ").strip()
        
        if choice in ['1', '2']:
            ip = VIEW_IP if choice == '1' else input("Enter Publisher IP: ").strip()
            if not ip: continue
            
            app = QApplication.instance() or QApplication(sys.argv)
            pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)
            
            try:
                cfg = RadarConfig(HW_CFG_FILE)
                window = LiveViewerWindow(cfg, ip)
                window.show()
                app.exec()
            except Exception as e:
                log.error(f"Failed to initialize: {e}")
                
        elif choice == '3':
            break

if __name__ == "__main__":
    main()