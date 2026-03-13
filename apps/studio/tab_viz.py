from PyQt6.QtWidgets import *
from PyQt6.QtCore import QTimer, Qt

# Enterprise architecture imports
from core.math import kinematics
from core.ui.theme import *
from core.io import storage, structs
from core.ui.widgets import MetricGraph, SkeletonLegend, HeavyTaskWorker

class VisualizerPage(QWidget):
    """
    The 3D Playback Engine.
    Renders the recorded skeleton using OpenGL and graphs dynamic 
    joint angles (like knee and hip flexion) in real-time.
    """
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        
        # ── State Tracking ──
        self.active_session = None
        self.frame_idx = 0
        self.playing = False
        self.is_initialized = False
        
        # Track the history of angles so the mini-graphs can draw a trailing line
        self.keys = [cfg[0] for cfg in METRIC_CONFIGS]
        self.history = {k: [] for k in self.keys}
        self.graphs = {}
        
        # ── Layout Setup ──
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Temporary loading label until OpenGL is booted by the studio.py timer
        self.loading_lbl = QLabel("Initializing Graphics Engine...")
        self.loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_lbl.setStyleSheet(f"color: {TEXT_DIM};")
        self.layout.addWidget(self.loading_lbl)
        
        self.viz = None
        
        # The QTimer acts as the "Play" button, ticking 30 times a second to update frames
        self.timer = QTimer()
        self.timer.timeout.connect(self.loop)

    def init_graphics(self):
        """
        Deferred initialization. OpenGL is heavy, so we wait to load it 
        until the rest of the application finishes booting.
        """
        if self.is_initialized: return
            
        from core.ui.render import SkeletonDisplay
        
        # Remove the temporary loading text
        self.loading_lbl.setParent(None)
        
        # ── 1. The 3D Viewport ──
        self.viz = SkeletonDisplay()
        self.layout.addWidget(self.viz, stretch=1)
        
        # ── 2. The Right Sidebar (Dashboard) ──
        dash_container = QWidget()
        dash_container.setFixedWidth(PANEL_WIDTH)
        dash_container.setStyleSheet(CSS_SIDEBAR)
        dash_layout = QVBoxLayout(dash_container)
        dash_layout.setContentsMargins(0, 0, 0, 0)
        dash_layout.setSpacing(0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(CSS_SIDEBAR + "margin: 0px; padding: 0px;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        self.grid = QGridLayout(scroll_content)
        self.grid.setContentsMargins(20, 20, 20, 20)
        self.grid.setSpacing(10)
        
        # Metadata Header
        self.info_box_widget = QWidget()
        info_lay = QVBoxLayout(self.info_box_widget)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.addWidget(QLabel("SESSION INFO", styleSheet=CSS_HEADER))
        self.info_vals = {}
        
        def add_info(lbl, key):
            """Helper to add clean key-value text rows to the dashboard."""
            row = QHBoxLayout()
            l = QLabel(lbl)
            l.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; border: none; background: transparent; ")
            v = QLabel("--")
            v.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 10px; font-weight: bold; border: none; background: transparent;")
            row.addWidget(l)
            row.addStretch()
            row.addWidget(v)
            info_lay.addLayout(row)
            self.info_vals[key] = v
            
        add_info("Subject", "lbl_subj")
        add_info("Activity", "lbl_act")
        add_info("FPS", "lbl_fps")
        add_info("Frames", "lbl_frames")
        add_info("Time", "lbl_time")
        
        self.grid.addWidget(self.info_box_widget, 0, 0, 1, 2)
        self.grid.addWidget(SkeletonLegend(), 1, 0, 1, 2)
        
        # ── 3. Build the Mini Metric Graphs ──
        row_idx = 2
        for i in range(0, len(METRIC_CONFIGS), 2):
            for col_idx in range(2):
                if i + col_idx < len(METRIC_CONFIGS):
                    key, title, color, min_v, max_v = METRIC_CONFIGS[i + col_idx]
                    graph = MetricGraph(title, color, min_v, max_v)
                    self.graphs[key] = graph
                    self.grid.addWidget(graph, row_idx, col_idx)
            row_idx += 1
        
        scroll.setWidget(scroll_content)
        dash_layout.addWidget(scroll)
        
        # ── 4. The Footer (Load Button) ──
        footer = QFrame()
        footer.setStyleSheet(CSS_SIDEBAR)
        f_lay = QVBoxLayout(footer)
        f_lay.setContentsMargins(10, 10, 10, 10)
        
        self.btn_load_ext = QPushButton("LOAD DATA")
        self.btn_load_ext.clicked.connect(self.load_external)
        self.btn_load_ext.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_ext.setStyleSheet(CSS_BTN_PRIMARY)
    
        f_lay.addWidget(self.btn_load_ext)
        dash_layout.addWidget(footer)
        
        self.layout.addWidget(dash_container)
        self.is_initialized = True

    # ── Background Loading Pipeline ──
    def _background_loader(self, filepath):
        """Helper function for the background thread to do the heavy lifting."""
        df, subj, act = storage.load_session_data(filepath)
        session = structs.df_to_session(df)
        return session, filepath, subj, act

    def load_external(self):
        """Spawns the background thread to prevent UI freezing on huge files."""
        fn, _ = QFileDialog.getOpenFileName(self, "Open Cleaned Data", "", "Data Files (*.parquet *.csv)")
        if fn:
            self.btn_load_ext.setEnabled(False)
            self.btn_load_ext.setText("LOADING...")
            
            # Spawn Background Thread
            self.worker = HeavyTaskWorker(self._background_loader, fn)
            self.worker.finished.connect(self._on_load_complete)
            self.worker.error.connect(self._on_load_error)
            self.worker.start()

    def _on_load_complete(self, result):
        """Callback when the background data is ready."""
        session, fn, subj, act = result
        self.btn_load_ext.setEnabled(True)
        self.btn_load_ext.setText("LOAD DATA")
        self.load_session(session, fn, subj, act)

    def _on_load_error(self, err):
        """Callback if the file is corrupted."""
        self.btn_load_ext.setEnabled(True)
        self.btn_load_ext.setText("LOAD DATA")
        QMessageBox.critical(self, "Error", f"Failed to load data:\n{str(err)}")

    # ── Playback Logic ──
    def load_session(self, session, filename="", subj="Unknown", act="Unknown"):
        """Prepares the engine to play the newly loaded data."""
        if not self.is_initialized: return
        
        self.active_session = session
        self.frame_idx = 0
        self.history = {k: [] for k in self.keys}
        
        # Update UI labels
        self.info_vals['lbl_subj'].setText(subj)
        self.info_vals['lbl_act'].setText(act)
        self.info_vals['lbl_fps'].setText(f"{session.fps:.1f}")
        self.info_vals['lbl_frames'].setText(str(len(session.frames)))
        
        self.viz.update_frame(None) 
        
        # Set the timer speed perfectly to match the recording FPS
        interval = int(1000 / session.fps) if session.fps > 0 else 33
        self.timer.setInterval(interval)
        
        # Auto-play on load
        self.playing = True
        self.timer.start()
        
        # Re-center the 3D camera so the runner is in the middle of the screen
        if session.frames:
            first_frame = session.frames[0]
            hip = kinematics.get_point(first_frame, "hip_mid")
            if hip: 
                self.viz.center_view(hip[0], -hip[1]) 
            self.viz.update_frame(first_frame)

    def toggle_play(self):
        """Play/Pause toggle (also hooked to Spacebar in studio.py)."""
        if not self.is_initialized: return
        self.playing = not self.playing
        if self.playing: self.timer.start()
        else: self.timer.stop()
        
    def step(self, delta):
        """Moves the playhead forward or backward by one frame."""
        if not self.is_initialized: return
        
        self.playing = False
        self.timer.stop() # Pause playback if user manually scrubs
        
        if not self.active_session: return
        
        # Modulo ensures the timeline wraps around perfectly if we go past the end or before 0
        self.frame_idx = (self.frame_idx + delta) % len(self.active_session.frames)
        self.loop(update_idx=False)

    def loop(self, update_idx=True):
        """The main playback engine tick. Updates the 3D skeleton and the mini-graphs."""
        if not self.active_session or not self.active_session.frames: return
            
        f = self.active_session.frames[self.frame_idx]
        
        # 1. Update OpenGL Skeleton
        self.viz.update_frame(f)
        
        # 2. Compute live angles (Trunk Lean, Knee flexion, etc.)
        vals = kinematics.compute_all_metrics(f)

        # 3. Update the mini-graphs in the sidebar
        for key in self.keys:
            if key in vals and key in self.graphs:
                self.history[key].append(vals[key])
                
                # Keep the graph history to a fixed rolling window so it doesn't look cluttered
                if len(self.history[key]) > MAX_HISTORY_LENGTH: 
                    self.history[key].pop(0)
                    
                self.graphs[key].update_data(self.history[key])
        
        # 4. Update Time Label
        self.info_vals['lbl_time'].setText(f"{f.timestamp:.1f}s")
        
        # 5. Advance the playhead
        if update_idx: 
            self.frame_idx = (self.frame_idx + 1) % len(self.active_session.frames)