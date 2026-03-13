import sys
import logging
import zmq
import json
import numpy as np
import scipy.ndimage as ndimage
import pyqtgraph as pg
import configparser

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                            QLabel, QStackedWidget)
from PyQt6.QtGui import QFont, QPixmap

# Pulling in custom settings from your new enterprise architecture
from core.radar.parser import RadarConfig
from core.ui.theme import * 

# Setup a logger so errors print cleanly to the terminal
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Subscriber")

# ── 1. Load Global Settings ──────────────────────────────────────────────────
# We read settings.ini here so if you ever change your network ports or UI colors,
# you don't have to hunt through Python code to fix it.
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

# ── 2. Background Network Threads ─────────────────────────────────────────────

class ZmqRadarWorker(QThread):
    """
    Background worker that constantly listens to Port 5555 for Radar bytes.
    It does the heavy math (FFT, decibel conversion, resizing) so the UI doesn't lag.
    """
    # Signals are how background threads safely talk to the UI thread.
    new_frame = pyqtSignal(np.ndarray, float, float) # Sends (Image Matrix, Dark_Limit, Light_Limit)
    error     = pyqtSignal(str)

    def __init__(self, cfg: RadarConfig, publisher_ip: str, zoom_y: float, zoom_x: float):
        super().__init__()
        self.cfg = cfg
        self.running = True
        self.zoom_y = zoom_y
        self.zoom_x = zoom_x
        
        # Calculate exactly how many bytes we expect in a single frame
        self.num_range_bins = cfg.numRangeBins
        self.num_vel_bins   = cfg.numLoops
        self.max_bin = min(int(MAX_RANGE / cfg.rangeRes), cfg.numRangeBins)
        self._expected_size = self.num_range_bins * self.num_vel_bins

        # Setup the ZeroMQ Subscriber socket
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(f"tcp://{publisher_ip}:{ZMQ_RADAR_PORT}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "") # Empty string means "Subscribe to ALL messages"

    def run(self):
        """This loop runs infinitely in the background until the app is closed."""
        while self.running:
            try:
                # poll(100) puts the thread to sleep for up to 100ms. 
                # If a message arrives, it wakes up instantly. This saves massive CPU usage.
                if self.socket.poll(100) == 0:
                    continue 

                # Grab the bytes and convert them to a 1D Numpy Array
                msg = self.socket.recv(flags=zmq.NOBLOCK)
                raw = np.frombuffer(msg, dtype=np.uint16)
                
                # Drop corrupted packets
                if raw.size != self._expected_size: continue

                # Reshape to 2D, chop off the distant ranges we don't care about, and convert to Decibels
                rd = raw.astype(np.float32).reshape(self.num_range_bins, self.num_vel_bins)
                rd = rd[:self.max_bin, :]
                display = 20.0 * np.log10(np.abs(np.fft.fftshift(rd, axes=1)) + 1e-6)
                
                # Smooth the image out to make it look nicer
                smooth = ndimage.zoom(display, (self.zoom_y, self.zoom_x), order=1)
                
                # Calculate exactly where the noise floor (black) and peak values (white/red) are
                lo = float(np.percentile(smooth, DISP_LOW_PCT))
                hi = float(np.percentile(smooth, DISP_HIGH_PCT))
                if lo >= hi: hi = lo + 0.1

                # Ship the finished product back to the Main UI Thread
                self.new_frame.emit(smooth, lo, hi)
                
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        """Safely shuts down the network socket when the user closes the window."""
        self.running = False
        self.wait()
        self.socket.close()
        self.context.term()


class ZmqCameraWorker(QThread):
    """
    Background worker listening to Port 5556 for the Camera stream.
    Expects a multipart message: [JSON Data, JPEG Bytes].
    """
    new_frame = pyqtSignal(dict, bytes)
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
                if self.socket.poll(100) == 0:
                    continue

                # Unpack the two parts of the message
                msg_parts = self.socket.recv_multipart(flags=zmq.NOBLOCK)
                if len(msg_parts) == 2:
                    meta_dict = json.loads(msg_parts[0].decode('utf-8'))
                    img_bytes = msg_parts[1]
                    
                    # Ship it to the UI
                    self.new_frame.emit(meta_dict, img_bytes)
                    
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        self.running = False
        self.wait()
        self.socket.close()
        self.context.term()

# ── 3. Main Window UI ────────────────────────────────────────────────────────
class LiveViewerWindow(QMainWindow):
    def __init__(self, cfg: RadarConfig, publisher_ip: str):
        super().__init__()
        self.cfg = cfg
        self.publisher_ip = publisher_ip
        
        # Track whether we've received the first frame yet
        self.radar_active = False
        self.cam_active = False
        
        self.zoom_y = 1.0
        self.zoom_x = 1.0

        self.setWindowTitle(f"OST Live Telemetry | Connected to: {self.publisher_ip}")
        self.resize(1400, 700)
        self.setStyleSheet(CSS_MAIN_WINDOW)

        # Precompute the math before the UI boots
        self._precompute_zoom() 
        self._build_ui()
        self._start_workers()

    def _precompute_zoom(self):
        """Calculates the scaling factors needed to make the radar blocky-pixels look smooth."""
        src_rows = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins)
        src_cols = self.cfg.numLoops
        self.zoom_y = max(SMOOTH_GRID, src_rows) / src_rows
        self.zoom_x = max(SMOOTH_GRID, src_cols) / src_cols

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        # A horizontal layout splits the window left-to-right
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20) 
        
        # ── Left Side: Radar Stack ──
        # A StackedWidget lets us put elements "on top" of each other. 
        self.radar_stack = QStackedWidget()
        
        # Layer 0: The "Waiting" message
        self.lbl_wait_radar = QLabel(f"Waiting for Radar Stream...\n(Listening on Port {ZMQ_RADAR_PORT})")
        self.lbl_wait_radar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_wait_radar.setFont(QFont("Segoe UI", 12))
        self.lbl_wait_radar.setStyleSheet(f"color: {TEXT_DIM}; background-color: {BG_PANEL}; border-radius: 8px;")
        
        # Layer 1: The actual PyQtGraph Plot
        self.plot_radar = pg.PlotWidget(title="Live Micro-Doppler Heatmap")
        self.plot_radar.setLabel("left", "Range", units="m", color=TEXT_DIM)
        self.plot_radar.setLabel("bottom", "Velocity", units="m/s", color=TEXT_DIM)
        self.plot_radar.showGrid(x=True, y=True, alpha=0.3)
        self.plot_radar.setBackground(BG_PANEL)
        
        # Adds a dotted center-line at Velocity = 0
        self.plot_radar.addItem(pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(TEXT_DIM, style=Qt.PenStyle.DashLine, width=1)))

        self.img_radar = pg.ImageItem()
        self.img_radar.setColorMap(pg.colormap.get(CMAP))
        self.plot_radar.addItem(self.img_radar)

        # Scale the image coordinates to actual meters and m/s
        max_bin = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins)
        self._rect = pg.QtCore.QRectF(-self.cfg.dopMax - self.cfg.dopRes / 2.0, 0, self.cfg.dopMax * 2.0, max_bin * self.cfg.rangeRes)
        self.img_radar.setRect(self._rect)

        self.radar_stack.addWidget(self.lbl_wait_radar) # Index 0
        self.radar_stack.addWidget(self.plot_radar)     # Index 1
        
        # stretch=1 enforces that this takes exactly 50% of the screen width
        main_layout.addWidget(self.radar_stack, stretch=1)

        # ── Right Side: Camera Stack ──
        self.cam_stack = QStackedWidget()
        
        # Layer 0: The "Waiting" message
        self.lbl_wait_cam = QLabel(f"Waiting for Camera Video Stream...\n(Listening on Port {ZMQ_CAM_PORT})")
        self.lbl_wait_cam.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_wait_cam.setFont(QFont("Segoe UI", 12))
        self.lbl_wait_cam.setStyleSheet(f"color: {TEXT_DIM}; background-color: {BG_PANEL}; border-radius: 8px;")
        
        # Layer 1: A simple label that we will aggressively paint JPEG images onto
        self.lbl_cam_feed = QLabel()
        self.lbl_cam_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cam_feed.setStyleSheet(f"background-color: {BG_PANEL}; border-radius: 8px;")
        
        self.cam_stack.addWidget(self.lbl_wait_cam)   # Index 0
        self.cam_stack.addWidget(self.lbl_cam_feed)  # Index 1
        
        # stretch=1 enforces that this takes exactly 50% of the screen width
        main_layout.addWidget(self.cam_stack, stretch=1)

    def _start_workers(self):
        """Boots up the background threads and connects their signals to the UI functions."""
        self.w_radar = ZmqRadarWorker(self.cfg, self.publisher_ip, self.zoom_y, self.zoom_x)
        self.w_radar.new_frame.connect(self._on_radar_frame)
        self.w_radar.start()

        self.w_cam = ZmqCameraWorker(self.publisher_ip)
        self.w_cam.new_frame.connect(self._on_cam_frame)
        self.w_cam.start()

    def _on_radar_frame(self, smooth_matrix: np.ndarray, lo: float, hi: float):
        """Triggered by the radar worker. Fast, light UI update."""
        if not self.radar_active:
            # First frame arrived! Flip the stacked widget from Layer 0 to Layer 1
            self.radar_stack.setCurrentIndex(1)
            self.radar_active = True

        self.img_radar.setImage(smooth_matrix, autoLevels=False, levels=(lo, hi))

    def _on_cam_frame(self, meta: dict, img_bytes: bytes):
        """Triggered by the camera worker. Fast JPEG rendering."""
        if not self.cam_active:
            # First frame arrived! Flip the stacked widget from Layer 0 to Layer 1
            self.cam_stack.setCurrentIndex(1)
            self.cam_active = True

        # Load the JPEG bytes into a standard Qt picture map
        pixmap = QPixmap()
        pixmap.loadFromData(img_bytes)
        
        # Dynamically scale the image to fit the right half of the window, preserving the aspect ratio
        lbl_w = self.lbl_cam_feed.width()
        lbl_h = self.lbl_cam_feed.height()
        if lbl_w > 0 and lbl_h > 0:
            self.lbl_cam_feed.setPixmap(pixmap.scaled(lbl_w, lbl_h, Qt.AspectRatioMode.KeepAspectRatio))

    def closeEvent(self, event):
        """Ensures the background threads die gracefully when the user hits the red 'X' button."""
        log.info("Closing viewer and safely killing ZMQ connections...")
        self.w_radar.stop()
        self.w_cam.stop()
        event.accept()

# ── 4. Bootstrapper ──────────────────────────────────────────────────────────
def main():
    """CLI Menu that asks for the IP address before booting the UI."""
    print("=========================================")
    print("        OST LIVE TELEMETRY VIEWER       ")
    print("=========================================")

    while True:
        print("\nCONNECTION MENU:")
        print(f"  1. Connect to Localhost ({VIEW_IP})")
        print("  2. Connect to External IP")
        print("  3. Exit")
        
        print("\nSelect an option (1-3): ", end="", flush=True)
        choice = input().strip()
        
        if choice in ['1', '2']:
            # Determine the IP address
            ip = VIEW_IP if choice == '1' else input("Enter Publisher IP: ").strip()
            if not ip: continue
            
            # Boot PyQt6
            app = QApplication.instance() or QApplication(sys.argv)
            pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)
            
            try:
                # Read the Radar Configuration file so we know how to plot the axes
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