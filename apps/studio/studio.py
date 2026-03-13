import sys
import os
import traceback

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QFrame, QLabel, QPushButton, QStackedWidget)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon

# Import the global color palette and UI metrics
from core.ui.theme import *

# Import the four independent analytical modules
from tab_prep import DataPrepPage
from tab_viz import VisualizerPage
from tab_gait import AnalysisPage
from tab_radar import RadarAnalysisPage

# ─────────────────────────────────────────────────────────────────────────────
#  Main Studio Window
# ─────────────────────────────────────────────────────────────────────────────
class UnifiedWorkstation(QMainWindow):
    """
    The main shell for the OST Studio. 
    It manages the top navigation bar and swaps between the 4 analytical tabs.
    """
    def __init__(self):
        super().__init__()
        
        # 1. Base Window Setup
        self.setWindowTitle(APP_NAME)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setStyleSheet(CSS_MAIN_WINDOW)
        
        if os.path.exists(ICON): 
            self.setWindowIcon(QIcon(ICON))
        
        # Create the central widget that holds everything
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0) # 0 spacing prevents ugly white gaps between the navbar and the content
        
        # 2. Build the Top Navigation Bar
        nav_bar = QFrame()
        nav_bar.setFixedHeight(50)
        nav_bar.setStyleSheet(CSS_NAVBAR)
        
        nav_lay = QHBoxLayout(nav_bar)
        nav_lay.setContentsMargins(20, 0, 20, 0)
        nav_lay.setSpacing(20)
        
        # App Title Logo
        title = QLabel("OST STUDIO")
        title.setStyleSheet(f"color: {ACCENT_COLOR}; font-weight: 900; font-size: 16px; margin-right: 20px; border: none;")
        nav_lay.addWidget(title)
        
        # Create the Navigation Buttons using our helper function
        self.btn_prep = self._nav_btn("DATA STUDIO")
        self.btn_viz = self._nav_btn("VISUALIZER")
        self.btn_analysis = self._nav_btn("ANALYSIS")
        self.btn_radar = self._nav_btn("RADAR ANALYSIS")
        
        # Connect clicks to the page swapper function
        self.btn_prep.clicked.connect(lambda: self.switch_page(0))
        self.btn_viz.clicked.connect(lambda: self.switch_page(1))
        self.btn_analysis.clicked.connect(lambda: self.switch_page(2))
        self.btn_radar.clicked.connect(lambda: self.switch_page(3))
        
        # Add buttons to the top bar
        nav_lay.addWidget(self.btn_prep)
        nav_lay.addWidget(self.btn_viz)
        nav_lay.addWidget(self.btn_analysis)
        nav_lay.addWidget(self.btn_radar)
        
        # Push the version number all the way to the right side
        nav_lay.addStretch()
        l_ver = QLabel(VERSION)
        l_ver.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; border: none; margin-top: 15px;")
        nav_lay.addWidget(l_ver)
        
        main_layout.addWidget(nav_bar)
        
        # 3. Initialize Stacked Pages (The Content Area)
        # QStackedWidget lets us stack the UI pages on top of each other and flip between them
        self.stack = QStackedWidget()
        
        # Instantiate the heavy page classes
        self.page_prep = DataPrepPage(self)
        self.page_viz = VisualizerPage(self) 
        self.page_analysis = AnalysisPage()
        self.page_radar = RadarAnalysisPage(self)
        
        # Add them to the stack (Index 0, 1, 2, 3)
        self.stack.addWidget(self.page_prep)
        self.stack.addWidget(self.page_viz)
        self.stack.addWidget(self.page_analysis)
        self.stack.addWidget(self.page_radar)
        
        main_layout.addWidget(self.stack)
        
        # Set default startup page
        self.switch_page(0)
        
        # PERFORMANCE TRICK: 
        # We wait 100 milliseconds *after* the UI finishes drawing to load the heavy 3D engine.
        # If we didn't do this, the app would freeze for 3 seconds before opening.
        QTimer.singleShot(100, self.boot_heavy_systems)

    def _nav_btn(self, text):
        """Helper to create standardized, checkable navigation buttons."""
        btn = QPushButton(text)
        btn.setCheckable(True) # Allows the button to stay highlighted when clicked
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # The CSS uses 'QPushButton:checked' to draw the blue line under the active tab
        btn.setStyleSheet(f"""
            QPushButton {{ color: {TEXT_DIM}; font-weight: bold; border: none; font-size: 12px; padding: 0 10px; height: 48px; }} 
            QPushButton:hover {{ color: {TEXT_MAIN}; }} 
            QPushButton:checked {{ color: {ACCENT_COLOR}; border-bottom: 2px solid {ACCENT_COLOR}; }}
        """)
        return btn

    def boot_heavy_systems(self):
        """Silent background boot for the OpenGL graphics engine."""
        try: 
            self.page_viz.init_graphics()
        except Exception:
            traceback.print_exc()

    def switch_page(self, index):
        """Changes the active stacked widget and highlights the correct button."""
        self.stack.setCurrentIndex(index)
        
        # Boolean evaluation: True if the index matches, False otherwise
        self.btn_prep.setChecked(index == 0)
        self.btn_viz.setChecked(index == 1)
        self.btn_analysis.setChecked(index == 2)
        self.btn_radar.setChecked(index == 3)
        
    def keyPressEvent(self, event):
        """Global Keyboard Shortcut Router."""
        # Only route playback keys if the user is actively on the Visualizer Tab
        if self.stack.currentIndex() == 1: 
            if event.key() == Qt.Key.Key_Space: 
                self.page_viz.toggle_play()
            elif event.key() == Qt.Key.Key_R: 
                # Reset playhead to frame 0
                self.page_viz.frame_idx = 0
                self.page_viz.loop(update_idx=False)
            elif event.key() == Qt.Key.Key_Left: 
                # Step backward 1 frame
                self.page_viz.step(-1)
            elif event.key() == Qt.Key.Key_Right: 
                # Step forward 1 frame
                self.page_viz.step(1)
                
        # Pass any unhandled keys back to the standard Qt event loop
        super().keyPressEvent(event)

# ─────────────────────────────────────────────────────────────────────────────
#  Bootstrapper
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = UnifiedWorkstation()
    w.show()
    sys.exit(app.exec())