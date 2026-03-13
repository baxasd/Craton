import traceback
import pyqtgraph as pg

from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import QThread, pyqtSignal
from core.ui.theme import *

# ── 1. Background Threading ──────────────────────────────────────────────────

class HeavyTaskWorker(QThread):
    """
    Runs heavy data/math tasks in the background without freezing the Main UI thread.
    This is the secret to keeping your application feeling fast and responsive 
    even while loading 100MB Parquet files or running Matrix math.
    """
    # Signals allow the background thread to safely pass data back to the UI
    finished = pyqtSignal(object)  
    error = pyqtSignal(str)        

    def __init__(self, task_function, *args, **kwargs):
        super().__init__()
        self.task_function = task_function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """This executes automatically on a separate CPU core when .start() is called."""
        try:
            # Execute the heavy math/loading function
            result = self.task_function(*self.args, **self.kwargs)
            # Ship the result back to the UI
            self.finished.emit(result)
        except Exception as e:
            # Print the exact line where the math crashed to the terminal
            traceback.print_exc()
            # Send the error string to the UI so it can show a Popup Message
            self.error.emit(str(e))

# ── 2. Reusable UI Components ────────────────────────────────────────────────

class MetricGraph(QWidget):
    """
    The compact, real-time line graphs used in the Visualizer Dashboard.
    Designed to update 30 times a second without lagging.
    """
    def __init__(self, title, color, min_v=0, max_v=180):
        super().__init__()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 15) 
        layout.setSpacing(4)
        
        # Header (Title on left, Live Value on right)
        header = QHBoxLayout()
        t_lbl = QLabel(title.upper())
        t_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; font-weight: bold; border: none;")
        
        self.v_lbl = QLabel("--")
        self.v_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold; border: none;")
        
        header.addWidget(t_lbl)
        header.addStretch()
        header.addWidget(self.v_lbl)
        layout.addLayout(header)
        
        # The Graph Canvas
        self.box = QFrame()
        self.box.setFixedHeight(80) 
        self.box.setStyleSheet(f"background-color: {BG_DARK}; border: 1px solid {BORDER}; border-radius: 4px;")
        box_lay = QVBoxLayout(self.box)
        box_lay.setContentsMargins(0, 0, 0, 0)
        
        self.plot = pg.PlotWidget()
        self.plot.setBackground(None)
        
        # Hide the numbers on the X and Y axis to keep the UI clean
        self.plot.hideAxis('bottom')
        self.plot.hideAxis('left')
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        
        # Lock user interactions so they can't accidentally pan/zoom the mini-graph
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.setYRange(min_v, max_v, padding=0.1)
        
        self.curve = self.plot.plot(pen=pg.mkPen(color, width=2))
        box_lay.addWidget(self.plot)
        layout.addWidget(self.box)

    def update_data(self, data_list):
        """Called by the visualizer loop to push the newest angle to the screen."""
        if not data_list: 
            return
            
        self.curve.setData(data_list)
        # Update the live text label with the most recent number
        self.v_lbl.setText(f"{int(data_list[-1])}°")


class SkeletonLegend(QFrame):
    """
    Simple, elegant color legend for the 3D visualizer.
    Tells the user which side of the body is Blue vs Orange.
    """
    def __init__(self):
        super().__init__()
        self.setStyleSheet("border: none; background: transparent;")
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 5, 0, 15)
        
        def add_item(name, color):
            box = QLabel()
            box.setFixedSize(10, 10)
            box.setStyleSheet(f"background-color: {color}; border-radius: 2px; border: none;")
            txt = QLabel(name)
            txt.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; border: none;")
            l.addWidget(box)
            l.addWidget(txt)
            l.addSpacing(10)
            
        add_item("Left", COLOR_BONE_LEFT)
        add_item("Right", COLOR_BONE_RIGHT)
        add_item("Center", COLOR_BONE_CENTER)
        l.addStretch()