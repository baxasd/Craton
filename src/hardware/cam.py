import logging
import pyrealsense2 as rs
import numpy as np
import configparser

# Hook into our standard logging system
log = logging.getLogger("RealSense")

class RealSenseCamera:
    """
    Hardware driver for the Intel RealSense Depth Camera.
    Handles stream configuration, frame alignment (matching 2D RGB to 3D Depth),
    and hardware-accelerated post-processing filters.
    """
    def __init__(self, width=640, height=480, fps=30):
        self.pipeline = None
        
        # ── Read Settings from INI ──
        config = configparser.ConfigParser()
        config.read('settings.ini')
        
        # Fallback to True and 156 if the user hasn't added these to the INI file yet
        auto_exposure = config.getboolean('Camera', 'auto_exposure', fallback=True)
        manual_exposure = config.getint('Camera', 'exposure', fallback=156)
        
        try:
            self.pipeline = rs.pipeline()
            self.config = rs.config()
            
            # Request specific streams from the hardware
            self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
            self.config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
            
            # Start the camera and grab the active profile
            self.profile = self.pipeline.start(self.config)
            
            # Mathematically warp the Depth map so it perfectly matches the RGB image
            self.align = rs.align(rs.stream.color)
            
            # ── HARDWARE FILTERS ──
            self.spatial = rs.spatial_filter()
            self.temporal = rs.temporal_filter()
            
            # ── EXPOSURE CONTROL ──
            self._configure_exposure(auto_exposure, manual_exposure)
            
            log.info(f"RealSense started successfully at {width}x{height} @ {fps} FPS")
            
        except Exception as e:
            log.error(f"Camera hardware initialization failed: {e}")
            self.pipeline = None

    def _configure_exposure(self, auto_exposure: bool, manual_exposure: int):
        """Dives into the physical camera sensors to configure lighting."""
        if not self.profile: return
        
        device = self.profile.get_device()
        for sensor in device.query_sensors():
            # We only want to change the exposure of the Color camera, not the Infrared laser
            if sensor.is_color_sensor():
                if auto_exposure:
                    sensor.set_option(rs.option.enable_auto_exposure, 1)
                    log.info("RGB Camera Auto-Exposure: ENABLED")
                else:
                    sensor.set_option(rs.option.enable_auto_exposure, 0)
                    sensor.set_option(rs.option.exposure, manual_exposure)
                    log.info(f"RGB Camera Auto-Exposure: DISABLED (Locked to {manual_exposure})")

    def get_frames(self):
        """Pulls the newest frame from the USB buffer, aligns it, and applies DSP filters."""
        if not self.pipeline: 
            return None, None
            
        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=1000)
            aligned = self.align.process(frames)
            
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            
            if not color_frame or not depth_frame: 
                return None, None
            
            depth_frame = self.spatial.process(depth_frame)
            depth_frame = self.temporal.process(depth_frame)
            
            return np.asanyarray(color_frame.get_data()), depth_frame
            
        except Exception as e:
            log.debug(f"Frame dropped or timeout: {e}")
            return None, None

    def stop(self):
        """Safely releases the USB port so other applications can use the camera."""
        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception as e:
                log.error(f"Error while stopping RealSense pipeline: {e}")