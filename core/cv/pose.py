import logging
import cv2
import mediapipe as mp

# Hook into our standard logging system
log = logging.getLogger("PoseEstimator")

class PoseEstimator:
    """
    Mediapipe Pose Estimator with aspect-ratio preserving resize.
    Standardizes inputs to a square (target_size) to ensure the AI 
    performs consistently regardless of the physical camera's aspect ratio.
    """
    def __init__(self, model_complexity=1, min_conf=0.5, target_size=512):
        self.target_size = target_size
        self.mp_pose = mp.solutions.pose
        
        # Initialize the heavy AI model in memory
        self.pose = self.mp_pose.Pose(
            static_image_mode=False, # False = Video mode (uses tracking across frames for speed)
            model_complexity=model_complexity,
            min_detection_confidence=min_conf,
            min_tracking_confidence=min_conf
        )

    def _resize_with_pad(self, img):
        """Resizes the image to target_size (square) while maintaining aspect ratio (Letterboxing)."""
        h, w = img.shape[:2]
        
        # Find the scale factor that fits the largest dimension into our target_size
        scale = self.target_size / max(h, w)
        nh, nw = int(h * scale), int(w * scale)

        # Resize the actual image data
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)

        # Calculate how much black padding is needed to make it a perfect square
        top = (self.target_size - nh) // 2
        bottom = self.target_size - nh - top
        left = (self.target_size - nw) // 2
        right = self.target_size - nw - left

        # Add the black borders
        padded = cv2.copyMakeBorder(resized, top, bottom, left, right,
                                    borderType=cv2.BORDER_CONSTANT, value=(0,0,0))

        return padded, scale, left, top

    def _restore_coords(self, landmarks, scale, pad_x, pad_y):
        """Maps normalized AI landmarks back to the original HD camera pixels."""
        restored = []
        for lm in landmarks:
            # MediaPipe returns normalized coordinates (0.0 to 1.0) based on the padded image.
            # 1. Multiply by target_size to get the exact pixel coordinate in the padded image.
            # 2. Subtract the padding to get the pixel coordinate in the resized image.
            # 3. Divide by scale to stretch it back up to the original 1080p/720p image size.
            x = (lm.x * self.target_size - pad_x) / scale
            y = (lm.y * self.target_size - pad_y) / scale
            z = lm.z / scale     
            
            restored.append((x, y, z))
            
        return restored

    def estimate(self, image):
        """
        Takes a raw camera frame and returns a list of (x, y, z) tuples in the ORIGINAL image pixels.
        Returns None if no human body is detected.
        """
        try:
            # OPTIMIZATION: Convert colorspace BEFORE padding. 
            # MediaPipe requires RGB, but OpenCV uses BGR. By converting here, 
            # we avoid wasting CPU time converting the pure black padding borders later.
            img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # 1. Pre-process (Resize & Pad)
            img_padded, scale, pad_x, pad_y = self._resize_with_pad(img_rgb)
            
            # 2. Inference (Feed it to the Neural Network)
            results = self.pose.process(img_padded)
            if not results.pose_landmarks:
                return None

            # 3. Post-process (Restore Coordinates back to raw Camera Space)
            return self._restore_coords(
                results.pose_landmarks.landmark, 
                scale, pad_x, pad_y
            )

        except Exception as e:
            log.error(f"MediaPipe inference failed: {e}")
            return None