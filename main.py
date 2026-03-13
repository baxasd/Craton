import sys
import os
import subprocess

# Ensure the root directory is in the Python path if running from source.
# This prevents "ModuleNotFoundError" when clicking the launcher buttons.
if not getattr(sys, 'frozen', False):
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (QGraphicsDropShadowEffect, QMainWindow, QWidget, 
                             QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QApplication, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor, QIcon, QPixmap

from core.ui.theme import *

class OSTLauncher(QMainWindow):
    """
    The Entry Point for the OST Suite.
    Spawns the Publisher, Viewer, and Studio as completely independent OS processes.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OST Suite")
        self.setFixedSize(350, 560) 
        self.setStyleSheet(f"QMainWindow {{ background-color: {BG_DARK}; }}")
        
        if os.path.exists(ICON):
            self.setWindowIcon(QIcon(ICON))
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 40, 30, 30)
        layout.setSpacing(15)
        
        # ── HEADER & LOGO ──
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(LOGO):
            pix = QPixmap(LOGO)
            scaled_pix = pix.scaled(300, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(scaled_pix)
        else:
            # Fallback text if the image file is missing
            logo_lbl.setText("OST")
            logo_lbl.setStyleSheet(f"color: {LAUNCHER_TITLE}; font-weight: 900; font-size: 56px;")
        layout.addWidget(logo_lbl)
        
        sub = QLabel("OSTEO-SKELETAL TRACKER")
        sub.setStyleSheet(f"color: {TEXT_MAIN}; font-weight: bold; font-size: 16px; letter-spacing: 2px; margin-bottom: 20px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)
        
        # ── LAUNCH BUTTONS ──
        
        # 1. Stream (CRITICAL FIX: is_cli=True so the terminal window actually appears)
        self.btn_stream = self._make_card("1. HARDWARE PUBLISHER", "Stream Radar & Camera Data", ACCENT_COLOR)
        self.btn_stream.clicked.connect(lambda: self._run_tool("stream.py", "stream", is_cli=True))
        layout.addWidget(self.btn_stream)

        # 2. Viewer (Live GUI)
        self.btn_view = self._make_card("2. LIVE TELEMETRY", "Monitor Streams over Network", ACCENT_COLOR)
        self.btn_view.clicked.connect(lambda: self._run_tool("view.py", "view", is_cli=False))
        layout.addWidget(self.btn_view)

        # 3. Studio (Post-Processing GUI)
        self.btn_studio = self._make_card("3. OST STUDIO", "Analyze Recorded Parquet Data", ACCENT_COLOR)
        self.btn_studio.clicked.connect(lambda: self._run_tool("studio.py", "studio", is_cli=False))
        layout.addWidget(self.btn_studio)
        
        layout.addStretch()
        
        # ── FOOTER ──
        ver = QLabel(f"{VERSION}")
        ver.setStyleSheet(f"color: {LAUNCHER_VER}; font-size: 10px; font-family: Consolas;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

    def _make_card(self, title, subtitle, accent_color):
        """Builds a beautiful, modern Windows 11 style hover-card."""
        btn = QPushButton()
        btn.setFixedHeight(85)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: {LAUNCHER_BTN_BG}; border: 1px solid {BORDER}; border-radius: 10px; text-align: left; padding-left: 20px; }}
            QPushButton:hover {{ background-color: {LAUNCHER_BTN_HOVER}; border: 1px solid {accent_color}; }}
            QPushButton:pressed {{ background-color: {LAUNCHER_BTN_PRESS}; }}
        """)
        
        lay = QVBoxLayout(btn)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(4)
        
        t = QLabel(title)
        t.setStyleSheet(f"color: {LAUNCHER_TITLE}; font-weight: bold; font-size: 13px; background: transparent; border: none;")
        t.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {LAUNCHER_SUBTITLE}; font-size: 11px; background: transparent; border: none;")
        s.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        lay.addWidget(t)
        lay.addWidget(s)
        
        # Apply standard soft drop shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 15))
        btn.setGraphicsEffect(shadow)
        
        return btn

    def _run_tool(self, script_name, exe_name, is_cli=False):
        """
        Subprocess Router.
        Knows how to launch the tools whether we are running as raw Python scripts (.py)
        or compiled PyInstaller binaries (.exe).
        """
        is_frozen = getattr(sys, 'frozen', False)
        env = os.environ.copy()
        
        # Flags for spawning a native command prompt window (Windows only)
        creation_flags = subprocess.CREATE_NEW_CONSOLE if (is_cli and os.name == 'nt') else 0
        
        if is_frozen:
            # PyInstaller creates a temporary _MEIPASS folder. 
            # We MUST remove these environment variables before spawning a child process,
            # otherwise the child will try to use the parent's temp folder and crash.
            env.pop('_MEIPASS2', None)
            env.pop('_MEIPASS', None)
            
            base_dir = os.path.dirname(sys.executable)
            exe_path = os.path.join(base_dir, f"{exe_name}.exe")
            
            if os.path.exists(exe_path):
                subprocess.Popen([exe_path], env=env, creationflags=creation_flags)
            else:
                QMessageBox.critical(self, "Error", f"Missing component:\n{exe_path}")
        else:
            # Running from source code (e.g., during development)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
            # The scripts live in the 'apps' folder
            full_path = os.path.join(base_dir, "apps", script_name)
            
            # Inject the root directory into the Python path so the child process can find 'core'
            env["PYTHONPATH"] = base_dir + os.pathsep + env.get("PYTHONPATH", "")
            
            if os.path.exists(full_path):
                subprocess.Popen([sys.executable, full_path], env=env, creationflags=creation_flags)
            else:
                QMessageBox.critical(self, "Error", f"Missing script at:\n{full_path}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    close_splash()
    w = OSTLauncher()
    w.show()
    sys.exit(app.exec())