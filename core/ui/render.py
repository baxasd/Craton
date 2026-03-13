import pyqtgraph as pg
from PyQt6.QtCore import Qt

from core.math import kinematics
from core.ui.theme import *

# ── 1. Skeleton Configuration ────────────────────────────────────────────────

# The specific joints we want to draw as circular dots on the screen.
# We exclude the face (eyes, ears) and hands (pinky, thumb) to keep the UI clean.
VISIBLE_NAMES = [
    "nose", 
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow", 
    "left_wrist", "right_wrist",
    "left_hip", "right_hip", 
    "left_knee", "right_knee", 
    "left_ankle", "right_ankle"
]

# The anatomical connections (lines) we want to draw between the joints.
# Notice we use the synthetic "hip_mid" and "shoulder_mid" joints calculated 
# by the kinematics engine to draw a stable spine.
BONES_LIST = [
    ("hip_mid", "shoulder_mid"),         # Spine
    ("hip_mid", "left_hip"),             # Pelvis L
    ("hip_mid", "right_hip"),            # Pelvis R
    ("shoulder_mid", "left_shoulder"),   # Clavicle L
    ("shoulder_mid", "right_shoulder"),  # Clavicle R
    
    ("left_shoulder", "left_elbow"),     # Arm L
    ("left_elbow", "left_wrist"),        # Forearm L
    ("right_shoulder", "right_elbow"),   # Arm R
    ("right_elbow", "right_wrist"),      # Forearm R
    
    ("left_hip", "left_knee"),           # Thigh L
    ("left_knee", "left_ankle"),         # Shin L
    ("right_hip", "right_knee"),         # Thigh R
    ("right_knee", "right_ankle"),       # Shin R
    
    ("shoulder_mid", "nose")             # Neck
]

# ── 2. The Rendering Engine ──────────────────────────────────────────────────

class SkeletonDisplay(pg.PlotWidget):
    """
    Hardware-accelerated 2D projection of the 3D skeleton.
    Subclasses pyqtgraph's PlotWidget to render vectors at 30+ FPS.
    """
    def __init__(self):
        super().__init__()
        
        # 1. Base Environment Setup
        self.setBackground(BG_DARK) 
        self.setAspectLocked(True) # Forces X and Y to scale equally so the human doesn't stretch
        self.showGrid(x=True, y=True, alpha=0.3)

        # 2. Center of Mass Tracking Line
        # A faint vertical line that follows the runner's hips to give a sense of forward momentum
        self.ref_line = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(GRID, width=2))
        self.addItem(self.ref_line)
        
        # 3. Geometry Caching
        self.bones = {} # Dictionary to store persistent line objects
        
        # ScatterPlotItem is highly optimized. We feed it all the joints at once 
        # instead of drawing 13 individual points.
        self.joints = pg.ScatterPlotItem(size=15, brush=pg.mkBrush(COLOR_JOINT), pen=pg.mkPen(BG_DARK, width=1))
        self.addItem(self.joints)

    def center_view(self, x, y):
        """Called when a new file loads to instantly snap the camera to the runner."""
        self.setRange(xRange=(x-1.0, x+1.0), yRange=(y-1.2, y+1.2), padding=0)

    def update_frame(self, f):
        """The main rendering loop. Called 30 times a second by the visualizer playback timer."""
        if not f: return
        
        # ── DRAW BONES ──
        for (n1, n2) in BONES_LIST:
            # Fetch the real-world metric coordinates from the math engine
            p1 = kinematics.get_point(f, n1)
            p2 = kinematics.get_point(f, n2)
            key = f"{n1}_{n2}"
            
            if p1 and p2:
                # Determine the bone color dynamically based on its anatomical side
                c = COLOR_BONE_CENTER
                if "left" in n1 or "left" in n2:
                    c = COLOR_BONE_LEFT
                elif "right" in n1 or "right" in n2:
                    c = COLOR_BONE_RIGHT
                
                # Lazy Instantiation: If this line doesn't exist yet, create it and add it to the scene
                if key not in self.bones:
                    self.bones[key] = pg.PlotCurveItem(pen=pg.mkPen(c, width=7, cap_style=Qt.PenCapStyle.RoundCap))
                    self.addItem(self.bones[key])
                
                # IMPORTANT Y-AXIS INVERSION:
                # In camera coordinate space, Y=0 is the top of the ceiling and grows downwards.
                # To make the runner stand upright on our graph, we multiply the Y coordinates by -1.
                self.bones[key].setData([p1[0], p2[0]], [-p1[1], -p2[1]])
            else:
                # DROPOUT HANDLING: If the camera lost tracking of a joint, hide the line instantly
                if key in self.bones:
                    self.bones[key].setData([], [])

        # ── DRAW JOINTS ──
        xs, ys = [], []
        for name in VISIBLE_NAMES:
            p = kinematics.get_point(f, name) 
            if p:
                xs.append(p[0])
                ys.append(-p[1]) # Apply the same Y-Axis inversion to the joints
                
        # Push the entire array of coordinates to the GPU at once
        self.joints.setData(xs, ys)

        # ── UPDATE TRACKING LINE ──
        hip = kinematics.get_point(f, "hip_mid")
        if hip:
            self.ref_line.setPos(hip[0])