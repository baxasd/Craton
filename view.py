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
import re
from rich.console import Console
from rich.prompt import Prompt
import time
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy
from PyQt6.QtGui import QPixmap, QIcon, QImage, QFont
from src.radar.parse import RadarConfig
from src.utils.theme import (
    ICON_PATH, SETTINGS_PATH, ROOT_DIR,
    COLOR_LEFT, COLOR_RIGHT, COLOR_CENTER, COLOR_CLEAN_DATA
)
from src.utils.config import ensure_config

ensure_config(SETTINGS_PATH)

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Viewer")

if getattr(sys, 'frozen', False):
    os.chdir(sys._MEIPASS)

config = configparser.ConfigParser(interpolation=None)
config.read(SETTINGS_PATH)

HW_CFG_FILE    = config['Hardware']['radar_cfg_file']
ZMQ_RADAR_PORT = config['Network'].get('zmq_radar_port', '5555')
ZMQ_CAM_PORT   = config['Network'].get('zmq_camera_port', '5556')
ZMQ_KEY_PORT   = config['Network'].get('zmq_key_port', '5554')

VIEW_IP        = config['Viewer']['default_ip']
MAX_RANGE      = float(config['Viewer']['max_range_m'])
CMAP           = config['Viewer']['cmap']
DISP_LOW_PCT   = float(config['Viewer']['low_pct'])
DISP_HIGH_PCT  = float(config['Viewer']['high_pct'])
SMOOTH_GRID    = int(config['Viewer']['smooth_grid_size'])

CLIENT_PUBLIC  = config['Security']['client_public'].encode('ascii')
CLIENT_SECRET  = config['Security']['client_secret'].encode('ascii')

# ── Design tokens — Syncing with theme.py & Streamlit ────────────────────────
def _load_st_theme():
    st_theme = {
        "primaryColor": "#BF0000",
        "backgroundColor": "#FFFFFF",
        "secondaryBackgroundColor": "#F3F4F5",
        "textColor": "#242024"
    }
    try:
        with open(os.path.join(ROOT_DIR, ".streamlit", "config.toml"), "r") as f:
            content = f.read()
            for k in st_theme.keys():
                match = re.search(fr'{k}\s*=\s*"([^"]+)"', content)
                if match:
                    st_theme[k] = match.group(1)
    except Exception:
        pass
    return st_theme

st_config = _load_st_theme()

C_LEFT    = COLOR_LEFT
C_RIGHT   = COLOR_RIGHT
C_CENTER  = COLOR_CENTER
C_GREEN   = COLOR_CLEAN_DATA

BG_BASE   = st_config["secondaryBackgroundColor"]
BG_SURF   = st_config["backgroundColor"]
BG_PANEL  = st_config["backgroundColor"]
BG_HDR    = st_config["secondaryBackgroundColor"]
BORDER    = "#E2E2E2"

TEXT_PRI  = st_config["textColor"]
TEXT_SEC  = "#605E5C"
TEXT_MUT  = "#A19F9D"
PRIMARY   = st_config["primaryColor"]

FONT      = "Inter"


# ── Network helper ────────────────────────────────────────────────────────────

def fetch_public_key(ip: str):
    ctx  = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, 5000)
    sock.connect(f"tcp://{ip}:{ZMQ_KEY_PORT}")
    try:
        sock.send_string("REQ_KEY")
        key = sock.recv()
        log.info(f"TOFU: key received from {ip}")
        return key
    except zmq.Again:
        log.error(f"TOFU: timeout {ip}:{ZMQ_KEY_PORT}")
        return None
    except Exception as e:
        log.error(f"TOFU: {e}")
        return None
    finally:
        sock.close()
        ctx.term()


# ── Workers (logic unchanged) ─────────────────────────────────────────────────

class ZmqRadarWorker(QThread):
    new_frame = pyqtSignal(np.ndarray, float, float)
    error     = pyqtSignal(str)

    def __init__(self, cfg: RadarConfig, ip: str, zoom_y: float, zoom_x: float):
        super().__init__()
        self.cfg      = cfg
        self.ip       = ip
        self.running  = True
        self.zoom_y   = zoom_y
        self.zoom_x   = zoom_x
        self.max_bin  = min(int(MAX_RANGE / cfg.rangeRes), cfg.numRangeBins)
        self._n_range = cfg.numRangeBins
        self._n_vel   = cfg.numLoops
        self._expected = self._n_range * self._n_vel
        self.ctx    = zmq.Context()
        self.socket = None

    def run(self):
        try:
            srv = fetch_public_key(self.ip)
            if srv is None:
                raise ConnectionError(f"No public key from {self.ip}")

            self.socket = self.ctx.socket(zmq.SUB)
            self.socket.curve_secretkey = CLIENT_SECRET
            self.socket.curve_publickey = CLIENT_PUBLIC
            self.socket.curve_serverkey = srv
            self.socket.connect(f"tcp://{self.ip}:{ZMQ_RADAR_PORT}")
            self.socket.setsockopt_string(zmq.SUBSCRIBE, "")
        except Exception as e:
            self.error.emit(str(e))
            return

        while self.running:
            try:
                if self.socket.poll(100) == 0:
                    continue
                msg = self.socket.recv(flags=zmq.NOBLOCK)
                raw = np.frombuffer(msg, dtype=np.uint16)
                if raw.size != self._expected:
                    continue
                rd      = raw.astype(np.float32).reshape(self._n_range, self._n_vel)
                rd      = rd[:self.max_bin, :]
                display = 20.0 * np.log10(np.abs(np.fft.fftshift(rd, axes=1)) + 1e-6)
                smooth  = ndimage.zoom(display, (self.zoom_y, self.zoom_x), order=1)
                lo      = float(np.percentile(smooth, DISP_LOW_PCT))
                hi      = float(np.percentile(smooth, DISP_HIGH_PCT))
                if lo >= hi:
                    hi = lo + 0.1
                self.new_frame.emit(smooth, lo, hi)
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        self.running = False
        self.wait()
        if self.socket:
            self.socket.close()
        self.ctx.term()


class ZmqCameraWorker(QThread):
    new_frame = pyqtSignal(dict, bytes, bytes)
    error     = pyqtSignal(str)

    def __init__(self, ip: str):
        super().__init__()
        self.ip      = ip
        self.running = True
        self.ctx     = zmq.Context()
        self.socket  = None

    def run(self):
        try:
            srv = fetch_public_key(self.ip)
            if srv is None:
                raise ConnectionError(f"No public key from {self.ip}")

            self.socket = self.ctx.socket(zmq.SUB)
            self.socket.curve_secretkey = CLIENT_SECRET
            self.socket.curve_publickey = CLIENT_PUBLIC
            self.socket.curve_serverkey = srv
            self.socket.connect(f"tcp://{self.ip}:{ZMQ_CAM_PORT}")
            self.socket.setsockopt_string(zmq.SUBSCRIBE, "")
        except Exception as e:
            self.error.emit(str(e))
            return

        while self.running:
            try:
                if self.socket.poll(100) == 0:
                    continue
                parts = self.socket.recv_multipart(flags=zmq.NOBLOCK)
                if len(parts) >= 2:
                    meta        = json.loads(parts[0].decode('utf-8'))
                    img_bytes   = parts[1]
                    depth_bytes = parts[2] if len(parts) == 3 else b''
                    self.new_frame.emit(meta, img_bytes, depth_bytes)
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        self.running = False
        self.wait()
        if self.socket:
            self.socket.close()
        self.ctx.term()


# ── UI components ─────────────────────────────────────────────────────────────

class FillLabel(QWidget):
    """Contain-mode image display — preserves aspect ratio without zooming or stretching.
    Uses KeepAspectRatio to fit the pixmap within the available space."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._lbl    = QLabel(self)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background: {BG_BASE};")

    def set_pixmap(self, px: QPixmap):
        self._pixmap = px
        self._repaint()

    def _repaint(self):
        if self._pixmap is None or not self.width() or not self.height():
            return
        w, h   = self.width(), self.height()
        scaled = self._pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._lbl.setPixmap(scaled)
        # Center the label within the widget
        lx = (w - scaled.width()) // 2
        ly = (h - scaled.height()) // 2
        self._lbl.setGeometry(lx, ly, scaled.width(), scaled.height())

    def resizeEvent(self, e):
        self._repaint()


class StatusDot(QWidget):
    """Hidden — functionality removed as per user request."""
    def __init__(self, color: str = C_GREEN, parent=None):
        super().__init__(parent)
        self.setFixedSize(0, 0)
        self.hide()


class Panel(QFrame):
    """MD3 surface-container card with a clean header bar."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setStyleSheet(f"""
            QFrame#Panel {{
                background: {BG_SURF};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hdr = QWidget()
        hdr.setFixedHeight(34)
        hdr.setStyleSheet(f"""
            background: {BG_HDR};
            border-bottom: 1px solid {BORDER};
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        hl.setSpacing(8)

        ttl = QLabel(title.upper())
        ttl.setStyleSheet(f"""
            color: {TEXT_SEC};
            font-family: '{FONT}';
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1.2px;
            background: transparent;
            border: none;
        """)
        hl.addWidget(ttl)
        hl.addStretch()

        outer.addWidget(hdr)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(0)
        outer.addLayout(self._body)

    def body(self) -> QVBoxLayout:
        return self._body


class MetricCard(QFrame):
    """MD3 surface-container card — single joint angle readout."""

    def __init__(self, label: str, accent: str = C_LEFT, parent=None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background: {BG_PANEL};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        name_lbl = QLabel(label.upper())
        name_lbl.setStyleSheet(f"""
            color: {TEXT_MUT};
            font-family: '{FONT}';
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 1.2px;
        """)

        self._val = QLabel("--")
        self._val.setStyleSheet(f"""
            color: {TEXT_PRI};
            font-family: '{FONT}';
            font-size: 24px;
            font-weight: 400;
            letter-spacing: -0.5px;
        """)

        unit_lbl = QLabel("°")
        unit_lbl.setStyleSheet(f"""
            color: {accent};
            font-family: '{FONT}';
            font-size: 12px;
            font-weight: 600;
        """)

        val_row = QHBoxLayout()
        val_row.setContentsMargins(0, 0, 0, 0)
        val_row.setSpacing(2)
        val_row.addWidget(self._val)
        val_row.addWidget(unit_lbl)
        val_row.addStretch()

        lay.addWidget(name_lbl)
        lay.addLayout(val_row)

    @property
    def value_label(self) -> QLabel:
        return self._val


# ── Main window ───────────────────────────────────────────────────────────────

class LiveViewerWindow(QMainWindow):
    """
    3-Column Light Layout with App Controls restored and refined widths:

      ┌────────────────────────────────────────────────────────────────────────┐
      │                                Top bar                                 │
      ├───────────────┬──────────┬─────────────────────────────────────────────┤
      │               │          │                                             │
      │    mmWave     │ Analytics│           RGB Camera (16:9)                 │
      │    Radar      │ (Narrow) │                                             │
      │               │          ├─────────────────────────────────────────────┤
      │               │          │                                             │
      │ (Col 1: 40%)  │(Col 2: 10%)│           Depth Map (16:9)                │
      │               │          ├─────────────────────────────────────────────┤
      │               │          │           App Controls                      │
      └───────────────┴──────────┴─────────────────────────────────────────────┘
    """

    def __init__(self, cfg: RadarConfig, ip: str):
        super().__init__()
        self.cfg           = cfg
        self.publisher_ip  = ip
        self.zoom_y        = 1.0
        self.zoom_x        = 1.0
        self.max_range_val = min(int(MAX_RANGE / cfg.rangeRes), cfg.numRangeBins) * cfg.rangeRes
        self.dop_max       = cfg.dopMax

        self.setWindowTitle(f"Craton Vision  ·  {ip}")
        self.resize(1500, 860)
        self.setMinimumSize(1200, 700)
        self.setWindowIcon(QIcon(ICON_PATH))

        self._precompute_zoom()
        self._apply_style()
        self._build_ui()
        self._start_workers()

    def _precompute_zoom(self):
        rows = min(int(MAX_RANGE / self.cfg.rangeRes), self.cfg.numRangeBins)
        cols = self.cfg.numLoops
        self.zoom_y = max(SMOOTH_GRID, rows) / rows
        self.zoom_x = max(SMOOTH_GRID, cols) / cols

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {BG_BASE};
                color: {TEXT_PRI};
                font-family: '{FONT}';
            }}
            QScrollBar {{ width: 0; height: 0; }}
        """)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(16, 16, 16, 16)
        body_lay.setSpacing(16)

        # ── COLUMN 1: RADAR (35% Width)
        radar_panel = Panel("mmWave Radar")
        self.plot_radar = self._make_radar_plot()
        radar_panel.body().addWidget(self.plot_radar)
        body_lay.addWidget(radar_panel, stretch=35)

        # ── COLUMN 2: VISION (50% Width)
        vision_stack = QVBoxLayout()
        vision_stack.setSpacing(16)

        rgb_panel = Panel("RGB Camera")
        self.cam_feed = FillLabel()
        rgb_panel.body().addWidget(self.cam_feed)
        vision_stack.addWidget(rgb_panel, stretch=1)

        depth_panel = Panel("Depth Map")
        self.depth_feed = FillLabel()
        depth_panel.body().addWidget(self.depth_feed)
        vision_stack.addWidget(depth_panel, stretch=1)

        body_lay.addLayout(vision_stack, stretch=50)

        # ── COLUMN 3: METRICS & STATUS (15% Width)
        info_stack = QVBoxLayout()
        info_stack.setSpacing(16)

        analytics_panel = Panel("Metrics")
        an_lay = QVBoxLayout()
        an_lay.setContentsMargins(10, 10, 10, 10)
        an_lay.setSpacing(10)

        self._card_l_elbow = MetricCard("L-Elbow", C_LEFT)
        self._card_r_elbow = MetricCard("R-Elbow", C_RIGHT)
        self._card_l_knee  = MetricCard("L-Knee",  C_LEFT)
        self._card_r_knee  = MetricCard("R-Knee",  C_RIGHT)

        an_lay.addWidget(self._card_l_elbow)
        an_lay.addWidget(self._card_r_elbow)
        an_lay.addWidget(self._card_l_knee)
        an_lay.addWidget(self._card_r_knee)
        an_lay.addStretch()
        
        analytics_panel.body().addLayout(an_lay)
        info_stack.addWidget(analytics_panel, stretch=4)

        status_panel = Panel("System Status")
        sl = QVBoxLayout()
        sl.setContentsMargins(12, 12, 12, 12)

        def make_lbl(text, color, bold=False):
            l = QLabel(text)
            fw = "700" if bold else "500"
            l.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: {fw};")
            return l

        sl.addWidget(make_lbl("STREAM IP", TEXT_MUT))
        sl.addWidget(make_lbl(self.publisher_ip, PRIMARY, bold=True))
        sl.addSpacing(8)
        sl.addWidget(make_lbl("HANDSHAKE", TEXT_MUT))
        sl.addWidget(make_lbl("CurveZMQ Secured", C_GREEN, bold=True))
        sl.addStretch()

        status_panel.body().addLayout(sl)
        info_stack.addWidget(status_panel, stretch=1)

        body_lay.addLayout(info_stack, stretch=15)

        root_lay.addWidget(body)

    # ── radar plot ────────────────────────────────────────────────────────────

    def _make_radar_plot(self) -> pg.PlotWidget:
        pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)

        plot = pg.PlotWidget()
        plot.setBackground(BG_SURF)
        plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        ax_style = {'color': TEXT_SEC, 'font-size': '10px', 'font-family': FONT}
        plot.setLabel("left",   "Range",    units="m",   **ax_style)
        plot.setLabel("bottom", "Velocity", units="m/s", **ax_style)
        plot.getPlotItem().hideAxis('top')
        plot.getPlotItem().hideAxis('right')

        for axis in ('left', 'bottom'):
            ax = plot.getAxis(axis)
            ax.setPen(pg.mkPen(color=BORDER, width=1))
            ax.setTextPen(pg.mkPen(color=TEXT_SEC))
            ax.setTickFont(QFont(FONT, 8))

        plot.showGrid(x=True, y=True, alpha=0.1)
        plot.setXRange(-self.dop_max, self.dop_max, padding=0)
        plot.setYRange(0, self.max_range_val, padding=0)

        self.img_radar = pg.ImageItem()
        self.img_radar.setColorMap(pg.colormap.get(CMAP))
        plot.addItem(self.img_radar)

        return plot

    # ── workers ───────────────────────────────────────────────────────────────

    def _start_workers(self):
        self.w_radar = ZmqRadarWorker(
            self.cfg, self.publisher_ip, self.zoom_y, self.zoom_x)
        self.w_radar.new_frame.connect(self._on_radar_frame)
        self.w_radar.start()

        self.w_cam = ZmqCameraWorker(self.publisher_ip)
        self.w_cam.new_frame.connect(self._on_cam_frame)
        self.w_cam.start()

    # ── frame handlers ────────────────────────────────────────────────────────

    def _on_radar_frame(self, smooth: np.ndarray, lo: float, hi: float):
        self.img_radar.setImage(smooth, autoLevels=False, levels=(lo, hi))
        self.img_radar.setRect(
            pg.QtCore.QRectF(-self.dop_max, 0, self.dop_max * 2.0, self.max_range_val))

    def _draw_clean_skeleton(self, frame, meta: dict):
        def hex_to_bgr(hx):
            hx = hx.lstrip('#')
            if len(hx) == 3:
                hx = ''.join([c*2 for c in hx])
            rgb = tuple(int(hx[i:i+2], 16) for i in (0, 2, 4))
            return (rgb[2], rgb[1], rgb[0])

        CV_LEFT   = hex_to_bgr(C_LEFT)
        CV_RIGHT  = hex_to_bgr(C_RIGHT)
        CV_CENTER = hex_to_bgr(C_CENTER)
        
        try:
            BLACK = hex_to_bgr(TEXT_PRI)
        except:
            BLACK = (48, 49, 50)
            
        GRAY      = (200, 198, 196)   # BORDER-ish

        # Pre-filter points present in meta to avoid repeated string formatting
        pts = {}
        for i in range(33):
            kx, ky = f"j{i}_px", f"j{i}_py"
            if kx in meta and ky in meta:
                pts[i] = (int(meta[kx]), int(meta[ky]))

        conns = [
            (0,1),(1,2),(2,3),(3,7),(0,4),(4,5),(5,6),(6,8),(9,10),
            (11,12),(11,13),(13,15),(15,17),(15,19),(15,21),(17,19),
            (12,14),(14,16),(16,18),(16,20),(16,22),(18,20),
            (11,23),(12,24),(23,24),
            (23,25),(25,27),(27,29),(29,31),(31,27),
            (24,26),(26,28),(28,30),(30,32),(32,28),
        ]

        for p1, p2 in conns:
            if p1 in pts and p2 in pts:
                cv2.line(frame, pts[p1], pts[p2], GRAY, 3, cv2.LINE_AA)

        for i, (cx, cy) in pts.items():
            color = CV_CENTER if i == 0 else (CV_LEFT if i % 2 != 0 else CV_RIGHT)
            cv2.circle(frame, (cx, cy), 5, BLACK, 1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), 4, color, -1, cv2.LINE_AA)

        return frame

    def _update_ui_metrics(self, meta: dict):
        joints = {
            'L_Elbow': (11, 13, 15, self._card_l_elbow),
            'R_Elbow': (12, 14, 16, self._card_r_elbow),
            'L_Knee':  (23, 25, 27, self._card_l_knee),
            'R_Knee':  (24, 26, 28, self._card_r_knee),
        }
        for _, (i1, i2, i3, card) in joints.items():
            if not all(f"j{i}_x" in meta for i in (i1, i2, i3)):
                continue
            v1 = np.array([meta[f"j{i1}_x"], meta[f"j{i1}_y"], meta[f"j{i1}_z"]])
            v2 = np.array([meta[f"j{i2}_x"], meta[f"j{i2}_y"], meta[f"j{i2}_z"]])
            v3 = np.array([meta[f"j{i3}_x"], meta[f"j{i3}_y"], meta[f"j{i3}_z"]])
            ba, bc   = v1 - v2, v3 - v2
            nba, nbc = np.linalg.norm(ba), np.linalg.norm(bc)
            if nba == 0 or nbc == 0:
                continue
            deg = int(np.degrees(np.arccos(np.clip(
                np.dot(ba, bc) / (nba * nbc), -1.0, 1.0))))
            card.value_label.setText(str(deg))

    def _on_cam_frame(self, meta: dict, img_bytes: bytes, depth_bytes: bytes):
        if img_bytes:
            self._update_ui_metrics(meta)
            arr   = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            frame = self._draw_clean_skeleton(frame, meta)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qt    = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
            self.cam_feed.set_pixmap(QPixmap.fromImage(qt))

        if depth_bytes:
            arr   = np.frombuffer(depth_bytes, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qt    = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
            self.depth_feed.set_pixmap(QPixmap.fromImage(qt))

    def closeEvent(self, event):
        self.w_radar.stop()
        self.w_cam.stop()
        event.accept()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    console.print("\n[bold]Craton Vision[/bold]\n")
    ip = Prompt.ask("Enter Stream IP", default=VIEW_IP).strip()

    app = QApplication.instance() or QApplication(sys.argv)
    font = QFont(FONT)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    try:
        with console.status("[dim]Connecting to streams...[/dim]", spinner="dots"):
            time.sleep(3)
            cfg    = RadarConfig(HW_CFG_FILE)
            window = LiveViewerWindow(cfg, ip)
        console.print("[green]✔[/green] [dim]Launching...[/dim]\n")
        window.show()
        app.exec()
    except Exception as e:
        console.print(f"\n[bold red]Fatal:[/bold red] {e}")
        log.error(e)


if __name__ == "__main__":
    main()