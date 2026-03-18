import sys
import logging
import os
import zmq
import json
import numpy as np
import scipy.ndimage as ndimage
import pyqtgraph as pg
import configparser

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QLabel
from PyQt6.QtGui import QPixmap, QIcon

from core.radar.parser import RadarConfig
from core.ui.theme import (
    COLOR_MAIN_BG,
    COLOR_TEXT,
    APP_VERSION,
    ICON_PATH,
    SETTINGS_PATH,
)

# Setup terminal logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Viewer")

if getattr(sys, "frozen", False):
    os.chdir(sys._MEIPASS)

# Load global configuration
config = configparser.ConfigParser(interpolation=None)
config.read(SETTINGS_PATH)

HW_CFG_FILE = config["Hardware"]["radar_cfg_file"]
ZMQ_RADAR_PORT = config["Network"].get("zmq_radar_port", "5555")
ZMQ_CAM_PORT = config["Network"].get("zmq_camera_port", "5556")

VIEW_IP = config["Viewer"]["default_ip"]
MAX_RANGE = float(config["Viewer"]["max_range_m"])
CMAP = config["Viewer"]["cmap"]
DISP_LOW_PCT = float(config["Viewer"]["low_pct"])
DISP_HIGH_PCT = float(config["Viewer"]["high_pct"])
SMOOTH_GRID = int(config["Viewer"]["smooth_grid_size"])

# Load Curve25519 encryption keys for the client
SERVER_PUBLIC = config["Security"]["server_public"].encode("ascii")
CLIENT_PUBLIC = config["Security"]["client_public"].encode("ascii")
CLIENT_SECRET = config["Security"]["client_secret"].encode("ascii")


class ZmqRadarWorker(QThread):
    """Background thread for receiving and processing encrypted radar matrices."""

    new_frame = pyqtSignal(np.ndarray, float, float)
    error = pyqtSignal(str)

    def __init__(
        self, cfg: RadarConfig, publisher_ip: str, zoom_y: float, zoom_x: float
    ):
        super().__init__()
        self.cfg = cfg
        self.running = True
        self.zoom_y = zoom_y
        self.zoom_x = zoom_x

        self.num_range_bins = cfg.numRangeBins
        self.num_vel_bins = cfg.numLoops
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

                if raw.size != self._expected_size:
                    continue

                # Calculate radar heatmap (dB) and upsample for rendering
                rd = raw.astype(np.float32).reshape(
                    self.num_range_bins, self.num_vel_bins
                )
                rd = rd[: self.max_bin, :]
                display = 20.0 * np.log10(np.abs(np.fft.fftshift(rd, axes=1)) + 1e-6)
                smooth = ndimage.zoom(display, (self.zoom_y, self.zoom_x), order=1)

                # Dynamic contrast scaling
                lo = float(np.percentile(smooth, DISP_LOW_PCT))
                hi = float(np.percentile(smooth, DISP_HIGH_PCT))
                if lo >= hi:
                    hi = lo + 0.1

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
    error = pyqtSignal(str)

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
                    meta_dict = json.loads(msg_parts[0].decode("utf-8"))
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
        self.setFixedSize(960, 400)
        self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {COLOR_MAIN_BG}; }}
            #CamFeed {{ background-color: transparent; border: none; }}
        """)

        # Cache physical bounds for the radar axes
        self.max_range_val = (
            min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins)
            * self.cfg.rangeRes
        )
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
        styles = {"color": COLOR_TEXT, "font-size": "12px", "font-family": "Segoe UI"}
        self.plot_radar.setLabel("left", "Range", units="m", **styles)
        self.plot_radar.setLabel("bottom", "Velocity", units="m/s", **styles)
        self.plot_radar.getPlotItem().hideAxis("top")
        self.plot_radar.getPlotItem().hideAxis("right")

        pen = pg.mkPen(color=COLOR_TEXT, width=1)
        self.plot_radar.getAxis("left").setPen(pen)
        self.plot_radar.getAxis("left").setTextPen(COLOR_TEXT)
        self.plot_radar.getAxis("bottom").setPen(pen)
        self.plot_radar.getAxis("bottom").setTextPen(COLOR_TEXT)
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
        self.lbl_cam_feed.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        main_layout.addWidget(self.lbl_cam_feed, stretch=1)

    def _start_workers(self):
        """Boot background networking threads."""
        self.w_radar = ZmqRadarWorker(
            self.cfg, self.publisher_ip, self.zoom_y, self.zoom_x
        )
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

    def _on_cam_frame(self, meta: dict, img_bytes: bytes):
        """Decode JPEG payload and update UI Pixmap."""
        pixmap = QPixmap()
        pixmap.loadFromData(img_bytes)

        lbl_w = self.lbl_cam_feed.width()
        lbl_h = self.lbl_cam_feed.height()
        if lbl_w > 0 and lbl_h > 0:
            self.lbl_cam_feed.setPixmap(
                pixmap.scaled(lbl_w, lbl_h, Qt.AspectRatioMode.KeepAspectRatio)
            )

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
