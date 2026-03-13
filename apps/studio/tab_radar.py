import logging
import numpy as np
import pyqtgraph as pg
import configparser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QFileDialog, QDoubleSpinBox, QComboBox, 
    QFrame, QCheckBox
)
from PyQt6.QtGui import QFont

from core.radar.parser import RadarConfig
from core.ui.theme import *
from core.radar.dsp import RecordingSession, extract_gait_metrics
from core.ui.widgets import HeavyTaskWorker

# Initialize a logger specific to this tab for clean debugging
log = logging.getLogger("RadarAnalyzer")

# ── 1. Load Global Settings ──────────────────────────────────────────────────
cfg_ini = configparser.ConfigParser()
cfg_ini.read('settings.ini')
HW_CFG_FILE   = cfg_ini['Hardware']['radar_cfg_file']
MAX_RANGE     = float(cfg_ini.get('Viewer', 'max_range_m', fallback='5.0'))
DISP_LOW_PCT  = float(cfg_ini.get('Viewer', 'low_pct',     fallback='40.0'))
DISP_HIGH_PCT = float(cfg_ini.get('Viewer', 'high_pct',    fallback='99.5'))

# Force PyQtGraph to use row-major memory mapping (matches NumPy, making it much faster)
pg.setConfigOptions(imageAxisOrder='row-major', antialias=True)

# ── 2. UI Helper Functions ───────────────────────────────────────────────────
def _line() -> QFrame:
    """Draws a subtle horizontal divider line in the sidebar."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"background-color: {BORDER}; margin: 5px 0px;")
    return line

def _header(text: str) -> QLabel:
    """Styles text as a clean, bold sidebar header."""
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #111827; margin-top: 5px;")
    return lbl

# ── 3. Main Radar Tab Widget ─────────────────────────────────────────────────
class RadarAnalysisPage(QWidget):
    """
    Loads raw Texas Instruments mmWave Parquet files, computes Fast Fourier Transforms (FFT)
    in the background, and plots the Micro-Doppler Spectrogram.
    """
    def __init__(self, parent_app=None):
        super().__init__()
        self.parent_app = parent_app
        
        # ── State Tracking ──
        self.session: RecordingSession | None = None
        self.radar_cfg: RadarConfig | None = None
        
        # Spectrogram and Axis Data
        self._spec: np.ndarray | None = None
        self._t_axis: np.ndarray | None = None
        self._v_axis: np.ndarray | None = None
        self._centroid: np.ndarray | None = None

        # Load the physical hardware constraints (so we know how to draw the Y-Axis velocity)
        try:
            self.radar_cfg = RadarConfig(HW_CFG_FILE)
        except Exception as e:
            log.warning(f"Radar config not loaded: {e}")

        self._build_ui()

    def _create_base_plot(self, y_lbl, x_lbl="Time (Seconds)"):
        """Instantiates the main PyqtGraph drawing board."""
        p = pg.PlotWidget()
        p.setBackground(BG_PANEL)
        p.setLabel('bottom', x_lbl, color=TEXT_DIM)
        p.setLabel('left', y_lbl, color=TEXT_DIM)
        p.showGrid(x=True, y=True, alpha=0.3) 
        p.getAxis('bottom').setPen(pg.mkPen(color=TEXT_DIM))
        p.getAxis('left').setPen(pg.mkPen(color=TEXT_DIM))
        
        # Draw a dotted center-line at Velocity = 0 m/s
        p.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(TEXT_DIM, style=Qt.PenStyle.DashLine, width=1)))
        return p

    def _make_graph_panel(self, title, desc, plot_widget):
        """Wraps the plot in our standard UI Card layout with a title and description."""
        card = QFrame()
        card.setStyleSheet(f"background-color: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 6px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(15, 15, 15, 15)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 14px; font-weight: bold; border: none;")
        lay.addWidget(lbl_title)
        
        lbl_desc = QLabel(desc)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; border: none; margin-bottom: 5px;")
        lay.addWidget(lbl_desc)
        
        plot_widget.setMinimumHeight(400)
        lay.addWidget(plot_widget)
        return card

    def _build_ui(self):
        """Constructs the left visualizer area and the right control sidebar."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Left Side: Scrolling Graph Area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet(f"background-color: {BG_DARK}; border: none;")
        self.graph_layout = QVBoxLayout(scroll_content)
        self.graph_layout.setContentsMargins(10, 10, 10, 10)
        self.graph_layout.setSpacing(10)
        
        self.p_radar = self._create_base_plot("Doppler Velocity (m/s)")
        self.spec_img = pg.ImageItem()
        self.p_radar.addItem(self.spec_img)
        self._set_cmap('jet') # Default to standard Jet heatmap colors

        # Overlay lines tracking the runner's exact physical velocity over time
        self.centroid_shadow = pg.PlotDataItem(pen=pg.mkPen(color=(0, 0, 0, 180), width=4)) # Black shadow for readability
        self.centroid_curve = pg.PlotDataItem(pen=pg.mkPen(color='#00E5FF', width=1.5))     # Cyan line
        self.p_radar.addItem(self.centroid_shadow)
        self.p_radar.addItem(self.centroid_curve)

        self.card_radar = self._make_graph_panel(
            "Micro-Doppler Spectrogram", 
            "Runner Velocity Profile over Time. The cyan overlay tracks the power-weighted mean body velocity.", 
            self.p_radar
        )
        self.graph_layout.addWidget(self.card_radar)
        self.graph_layout.addStretch()

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, stretch=1)

        # ── Right Side: Control Sidebar ──
        ctrl_panel = QFrame()
        ctrl_panel.setFixedWidth(PANEL_WIDTH)
        ctrl_panel.setStyleSheet(CSS_SIDEBAR)
        ctrl_lay = QVBoxLayout(ctrl_panel)
        ctrl_lay.setContentsMargins(20, 20, 20, 20)
        ctrl_lay.setSpacing(10)
        ctrl_lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 1. File Loader
        ctrl_lay.addWidget(QLabel("DATA SOURCE", styleSheet=CSS_HEADER))
        self.btn_open = QPushButton("Select Parquet File")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setStyleSheet(CSS_BTN_PRIMARY)
        self.btn_open.clicked.connect(self._open_file)
        ctrl_lay.addWidget(self.btn_open)

        self.lbl_file = QLabel("No file selected")
        self.lbl_file.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 10px; border: none;")
        self.lbl_file.setWordWrap(True)
        ctrl_lay.addWidget(self.lbl_file)
        ctrl_lay.addWidget(_line())

        # 2. Status Output
        ctrl_lay.addWidget(QLabel("SESSION INFO", styleSheet=CSS_HEADER))
        self.lbl_summary = QLabel("Duration: --\nFrames: --\nResolution: --")
        self.lbl_summary.setStyleSheet(f"color: {TEXT_DIM}; line-height: 1.5; font-size: 11px; border: none;")
        ctrl_lay.addWidget(self.lbl_summary)
        ctrl_lay.addWidget(_line())

        # 3. DSP Configuration (Range Gating)
        ctrl_lay.addWidget(QLabel("RANGE GATE (M)", styleSheet=CSS_HEADER))
        gate_lay = QHBoxLayout()
        self.spn_lo = QDoubleSpinBox()
        self.spn_lo.setRange(0, 49); self.spn_lo.setSingleStep(0.1); self.spn_lo.setValue(0.0)
        self.spn_lo.setStyleSheet(CSS_INPUT)
        self.spn_hi = QDoubleSpinBox()
        self.spn_hi.setRange(0.1, 50); self.spn_hi.setSingleStep(0.1); self.spn_hi.setValue(MAX_RANGE)
        self.spn_hi.setStyleSheet(CSS_INPUT)
        
        gate_lay.addWidget(self.spn_lo)
        dash_lbl = QLabel("-"); dash_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none;")
        gate_lay.addWidget(dash_lbl)
        gate_lay.addWidget(self.spn_hi)
        ctrl_lay.addLayout(gate_lay)

        self.btn_apply = QPushButton("Apply Filter")
        self.btn_apply.setStyleSheet(CSS_BTN_OUTLINE)
        self.btn_apply.clicked.connect(self._recompute)
        ctrl_lay.addWidget(self.btn_apply)
        ctrl_lay.addWidget(_line())

        # 4. Visual Adjustments (These update instantly without re-running DSP)
        ctrl_lay.addWidget(QLabel("VISUALS", styleSheet=CSS_HEADER))
        
        cmap_lay = QHBoxLayout()
        lbl_theme = QLabel("Theme:"); lbl_theme.setStyleSheet(f"color: {TEXT_DIM}; border: none;")
        cmap_lay.addWidget(lbl_theme)
        self.cmb_cmap = QComboBox()
        self.cmb_cmap.addItems(['turbo', 'inferno', 'viridis', 'plasma', 'magma', 'jet', 'white-red'])
        self.cmb_cmap.setCurrentText('jet')
        self.cmb_cmap.setStyleSheet(CSS_INPUT)
        self.cmb_cmap.currentTextChanged.connect(self._on_cmap_changed)
        cmap_lay.addWidget(self.cmb_cmap)
        ctrl_lay.addLayout(cmap_lay)

        cont_lay = QHBoxLayout()
        lbl_cont = QLabel("Contrast:"); lbl_cont.setStyleSheet(f"color: {TEXT_DIM}; border: none;")
        cont_lay.addWidget(lbl_cont)
        self.spn_low = QDoubleSpinBox(); self.spn_low.setRange(0, 98); self.spn_low.setValue(DISP_LOW_PCT); self.spn_low.setStyleSheet(CSS_INPUT)
        self.spn_high = QDoubleSpinBox(); self.spn_high.setRange(2, 100); self.spn_high.setValue(DISP_HIGH_PCT); self.spn_high.setStyleSheet(CSS_INPUT)
        # Tie the contrast spinboxes directly to the fast level refresher
        self.spn_low.valueChanged.connect(self._refresh_levels)
        self.spn_high.valueChanged.connect(self._refresh_levels)
        cont_lay.addWidget(self.spn_low)
        cont_lay.addWidget(self.spn_high)
        ctrl_lay.addLayout(cont_lay)

        smooth_lay = QHBoxLayout()
        lbl_smooth = QLabel("Smoothing:"); lbl_smooth.setStyleSheet(f"color: {TEXT_DIM}; border: none;")
        smooth_lay.addWidget(lbl_smooth)
        self.spn_smooth = QDoubleSpinBox(); self.spn_smooth.setRange(1, 10); self.spn_smooth.setValue(3); self.spn_smooth.setDecimals(0)
        self.spn_smooth.setStyleSheet(CSS_INPUT)
        smooth_lay.addWidget(self.spn_smooth)
        ctrl_lay.addLayout(smooth_lay)

        self.chk_centroid = QCheckBox("Overlay Cadence Line")
        self.chk_centroid.setChecked(True)
        self.chk_centroid.setStyleSheet(CSS_CHECKBOX)
        self.chk_centroid.stateChanged.connect(self._toggle_centroid)
        ctrl_lay.addWidget(self.chk_centroid)

        line4 = QFrame(); line4.setFixedHeight(1); line4.setStyleSheet(f"background-color: {BORDER};")
        ctrl_lay.addWidget(line4)

        # 5. Output Statistics
        ctrl_lay.addWidget(QLabel("GAIT STATISTICS", styleSheet=CSS_HEADER))
        self.lbl_stats = QLabel("Peak Velocity: --\nMean |Vel|: --\nCadence: --")
        self.lbl_stats.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 12px; line-height: 1.8; border: none;")
        ctrl_lay.addWidget(self.lbl_stats)

        ctrl_lay.addStretch()
        main_layout.addWidget(ctrl_panel)

    def _set_cmap(self, name: str):
        """Translates the dropdown text into actual PyqtGraph color maps."""
        if name == 'white-red':
            positions = np.array([0.0, 0.4, 1.0])
            colors = np.array([[255, 255, 255, 255], [255, 69, 0, 255], [139, 0, 0, 255]], dtype=np.ubyte)
            self.spec_img.setColorMap(pg.ColorMap(positions, colors))
        elif name == 'jet':
            positions = np.array([0.0, 0.125, 0.375, 0.625, 0.875, 1.0])
            colors = np.array([[0, 0, 127, 255], [0, 0, 255, 255], [0, 255, 255, 255],
                               [255, 255, 0, 255], [255, 0, 0, 255], [127, 0, 0, 255]], dtype=np.ubyte)
            self.spec_img.setColorMap(pg.ColorMap(positions, colors))
        else:
            try: cmap = pg.colormap.get(name)
            except Exception: cmap = pg.colormap.get('inferno')
            self.spec_img.setColorMap(cmap)

    # ── 4. Workflow Pipeline (Load -> DSP -> Render) ─────────────────────────
    def _open_file(self):
        """Step 1: Parse the raw Hexadecimal arrays from disk."""
        path, _ = QFileDialog.getOpenFileName(self, "Open Parquet", "records", "Parquet files (*.parquet)")
        if not path: return
        
        self.lbl_file.setText(Path(path).name)
        self.lbl_summary.setText("Loading huge binary file...\nPlease wait.")
        self.btn_open.setEnabled(False)
        
        # Load via background thread to prevent UI freezing
        self.load_worker = HeavyTaskWorker(RecordingSession, path, self.radar_cfg)
        self.load_worker.finished.connect(self._on_load_complete)
        self.load_worker.error.connect(self._on_load_error)
        self.load_worker.start()

    def _on_load_complete(self, session):
        """Triggered when the file is fully loaded into RAM."""
        self.session = session
        fps = session.num_frames / session.duration_s if session.duration_s > 0 else 0
        
        self.lbl_summary.setText(
            f"<b>Duration:</b> {session.duration_s:.1f} s ({session.num_frames} frames)<br>"
            f"<b>Sampling:</b> {fps:.1f} Hz<br>"
            f"<b>Resolution:</b> {self.radar_cfg.dopRes:.3f} m/s"
        )
        self.btn_open.setEnabled(True)
        self.btn_apply.setEnabled(True)
        
        # Automatically advance to Step 2
        self._recompute()

    def _on_load_error(self, err):
        log.error(err)
        self.lbl_summary.setText(f"Error: {err}")
        self.btn_open.setEnabled(True)

    def _recompute(self):
        """Step 2: Run heavy FFT math to turn the 1D arrays into 2D Doppler velocities."""
        if not self.session: return
        self.btn_apply.setEnabled(False)
        self.btn_apply.setText("Computing FFTs...")
        
        # DSP Math via background thread
        self.calc_worker = HeavyTaskWorker(
            self.session.build_spectrogram, 
            self.spn_lo.value(), self.spn_hi.value(), int(self.spn_smooth.value())
        )
        self.calc_worker.finished.connect(self._on_recompute_complete)
        self.calc_worker.error.connect(self._on_recompute_error)
        self.calc_worker.start()

    def _on_recompute_complete(self, result):
        """Triggered when the spectrogram math finishes."""
        self._spec, self._t_axis, self._v_axis, self._centroid = result
        
        # Advance to Step 3
        self._render()
        self._update_stats()
        
        self.btn_apply.setEnabled(True)
        self.btn_apply.setText("Apply Filter")

    def _on_recompute_error(self, err):
        log.error(err)
        self.btn_apply.setEnabled(True)
        self.btn_apply.setText("Apply Filter")

    # ── 5. Render Optimizations ──────────────────────────────────────────────
    def _get_contrast_levels(self):
        """
        OPTIMIZATION: Calculates the black (noise) and white (peak signal) values.
        By subsampling the array (skipping every 4 pixels), this runs 16x faster
        and prevents the UI from lagging when dragging the contrast spinboxes!
        """
        if self._spec is None: return 0, 1
        sub_spec = self._spec[::4, ::4] # Decimation trick
        
        lo = float(np.percentile(sub_spec, self.spn_low.value()))
        hi = float(np.percentile(sub_spec, self.spn_high.value()))
        if lo >= hi: hi = lo + 0.1 # Safety catch to prevent divide-by-zero graphics errors
        return lo, hi

    def _render(self):
        """Step 3: Paints the math onto the screen."""
        if self._spec is None: return
        
        lo, hi = self._get_contrast_levels()

        # PyqtGraph expects X,Y matrices to be transposed compared to NumPy
        img_data = self._spec.T
        self.spec_img.setImage(img_data, autoLevels=False, levels=(lo, hi))

        # We must manually scale the image so the pixels align perfectly with the Time and Velocity Axes
        dt = (self._t_axis[-1] - self._t_axis[0]) / img_data.shape[1]
        dv = (self._v_axis[-1] - self._v_axis[0]) / img_data.shape[0]

        from PyQt6.QtGui import QTransform
        tr = QTransform()
        tr.translate(self._t_axis[0], self._v_axis[0]) # Start at time 0 and lowest negative velocity
        tr.scale(dt, dv)
        self.spec_img.setTransform(tr)

        # Lock the scrolling bounds
        self.p_radar.setLimits(xMin=self._t_axis[0], xMax=self._t_axis[-1], yMin=self._v_axis[0], yMax=self._v_axis[-1])
        self.p_radar.setXRange(self._t_axis[0], self._t_axis[-1], padding=0)
        self.p_radar.setYRange(self._v_axis[0], self._v_axis[-1], padding=0)

        # Draw the centroid (The center of the runner's mass)
        if self._centroid is not None:
            self.centroid_shadow.setData(x=self._t_axis, y=self._centroid)
            self.centroid_curve.setData(x=self._t_axis, y=self._centroid)
            is_visible = self.chk_centroid.isChecked()
            self.centroid_shadow.setVisible(is_visible)
            self.centroid_curve.setVisible(is_visible)

    def _refresh_levels(self):
        """Fast UI trigger when the user clicks the contrast spinboxes."""
        if self._spec is None: return
        lo, hi = self._get_contrast_levels()
        self.spec_img.setLevels((lo, hi))

    def _on_cmap_changed(self, name: str):
        self._set_cmap(name)

    def _toggle_centroid(self):
        if self._centroid is not None:
            is_visible = self.chk_centroid.isChecked()
            self.centroid_shadow.setVisible(is_visible)
            self.centroid_curve.setVisible(is_visible)

    def _update_stats(self):
        """Executes the `extract_gait_metrics` logic to estimate SPM and velocity."""
        if self._spec is None: return
        
        peak_v, mean_abs, spm = extract_gait_metrics(self._spec, self._t_axis, self._v_axis)

        cadence_str = "--"
        if spm > 0:
            cadence_str = f"<span style='color: {ACCENT_COLOR}; font-weight: bold;'>{spm:.0f} SPM</span>"

        self.lbl_stats.setText(
            f"<b>Peak Velocity:</b> {peak_v:+.2f} m/s<br>"
            f"<b>Mean |Vel|:</b> {mean_abs:.2f} m/s<br>"
            f"<b>Est. Cadence:</b> {cadence_str}"
        )