import logging
import numpy as np
import pyrealsense2 as rs

# Hook into our standard logging system
log = logging.getLogger("DepthMath")

def get_mean_depth(depth_frame, px: int, py: int, w: int, h: int, patch: int = 1):
    """
    Calculates the average depth in a small grid (patch) around a specific pixel.
    
    Why use a patch? Infrared depth sensors often have "holes" (pixels that return 0.0) 
    if the laser hits a reflective surface or a sharp edge. By looking at a 3x3 
    pixel grid (patch=1), we guarantee we get an accurate depth reading even if the 
    exact center pixel failed to register.
    """
    try:
        # 1. Safety Check: Ensure the hardware actually handed us a Depth Frame (not a Color frame)
        if not depth_frame.is_depth_frame():
            return None
        
        # 2. Cast to an explicit depth_frame object to unlock the .get_distance() method
        depth_frame = depth_frame.as_depth_frame() 
        
        values = []
        
        # 3. Loop through the grid (If patch=1, this checks from -1 to +1 on X and Y)
        for dx in range(-patch, patch + 1):
            for dy in range(-patch, patch + 1):
                # Calculate the exact pixel coordinate for this neighbor
                x, y = px + dx, py + dy
                
                # Boundary Check: Ensure we aren't asking for a pixel off the edge of the screen
                if 0 <= x < w and 0 <= y < h:
                    
                    # Ask the RealSense API for the depth in meters
                    d = depth_frame.get_distance(x, y)
                    
                    # Ignore 0.0 values (Infrared "holes" / missing data)
                    if d > 0:
                        values.append(d)
                        
        # 4. Return the average of all valid nearby pixels
        return float(np.mean(values)) if values else None
        
    except Exception as e:
        # Fail silently if the hardware glitches, so we don't crash the video stream
        log.debug(f"Depth extraction failed for pixel ({px}, {py}): {e}")
        return None

def deproject_pixel_to_point(depth_intrin, px: int, py: int, depth: float):
    """
    Converts a flat 2D screen coordinate (X, Y) into a real-world 3D coordinate (X, Y, Z).
    
    Args:
        depth_intrin: The physical lens properties of the RealSense camera (Focal length, distortion).
        px, py: The 2D pixel coordinates on the screen.
        depth: The real-world distance to that pixel in meters (calculated above).
        
    Returns:
        A list [x, y, z] representing real-world meters from the center of the camera lens.
    """
    try:
        # rs2_deproject_pixel_to_point is an internal C++ math function provided by Intel.
        # It uses trigonometry and the physical curvature of the camera lens to pinpoint
        # exactly where the object is in 3D space.
        return rs.rs2_deproject_pixel_to_point(depth_intrin, [px, py], depth)
        
    except Exception as e:
        log.debug(f"Deprojection error at pixel ({px}, {py}): {e}")
        return None