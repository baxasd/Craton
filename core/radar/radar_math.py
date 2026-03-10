import logging
import numpy as np
import pyarrow.parquet as pq
import scipy.ndimage as ndimage
from scipy.signal import butter, filtfilt, find_peaks

from core.radar.base import RadarConfig

log = logging.getLogger("RadarMath")

def butter_bandpass_filter(data, lowcut, highcut, fs, order=4):
    """Applies a bandpass filter to isolate human step frequencies."""
    nyq = 0.5 * fs
    b, a = butter(order, [lowcut / nyq, highcut / nyq], btype='band')
    return filtfilt(b, a, data)


class RecordingSession:
    def __init__(self, filepath: str, cfg: RadarConfig):
        self.filepath = filepath
        self.cfg = cfg
        self.frames: list[np.ndarray] = []
        self.timestamps: list[float] = []
        self._load()

    def _load(self):
        """Loads and extracts raw RDHM matrices from the Parquet file."""
        table = pq.read_table(self.filepath)
        df = table.to_pandas()
        exp = self.cfg.numRangeBins * self.cfg.numLoops
        
        for _, row in df.iterrows():
            raw = np.frombuffer(row['rdhm_bytes'], dtype=np.uint16)
            if raw.size != exp: continue
            mat = raw.astype(np.float32).reshape(self.cfg.numRangeBins, self.cfg.numLoops)
            self.frames.append(mat)
            self.timestamps.append(float(row['timestamp']))

    @property
    def num_frames(self): 
        return len(self.frames)

    @property
    def duration_s(self):
        return (self.timestamps[-1] - self.timestamps[0]) if len(self.timestamps) > 1 else 0.0

    def build_spectrogram(self, gate_lo_m: float, gate_hi_m: float, smooth_t: int = 2):
        """
        Collapses the range gate, mitigates clutter, interpolates velocity, 
        and extracts the centroid center of mass.
        """
        cfg = self.cfg
        lo_bin = max(0, int(gate_lo_m / cfg.rangeRes))
        hi_bin = min(cfg.numRangeBins, max(lo_bin + 1, int(gate_hi_m / cfg.rangeRes)))
        nv = cfg.numLoops

        v_axis_coarse = np.linspace(-cfg.dopMax, cfg.dopMax, nv, dtype=np.float32)
        spec_lin = np.zeros((self.num_frames, nv), dtype=np.float32)

        for i, mat in enumerate(self.frames):
            sl = mat[lo_bin:hi_bin, :].max(axis=0)
            spec_lin[i, :] = np.abs(np.fft.fftshift(sl))

        # Centroid extraction
        noise_lin = np.percentile(spec_lin, 30, axis=1, keepdims=True)
        weights = np.maximum(spec_lin - noise_lin, 0.0)
        w_sum = weights.sum(axis=1)
        centroid = np.where(w_sum > 1e-9, (weights * v_axis_coarse[np.newaxis, :]).sum(axis=1) / w_sum, 0.0).astype(np.float32)

        # Convert to dB and mitigate stationary clutter
        spec_db = 20.0 * np.log10(spec_lin + 1e-9)
        center_idx = nv // 2
        moving_bins_db = np.delete(spec_db, [center_idx-1, center_idx, center_idx+1], axis=1)
        clutter_ceiling = np.percentile(moving_bins_db, 99.0)
        spec_db[:, center_idx-1:center_idx+2] = np.clip(spec_db[:, center_idx-1:center_idx+2], a_min=None, a_max=clutter_ceiling)

        # Smoothing and Upsampling
        if smooth_t > 1:
            spec_db = ndimage.uniform_filter1d(spec_db, size=smooth_t, axis=0)

        zoom_factor = 8
        spec_db = ndimage.zoom(spec_db, (1, zoom_factor), order=3)
        v_axis_highres = np.linspace(-cfg.dopMax, cfg.dopMax, nv * zoom_factor, dtype=np.float32)

        t0 = self.timestamps[0]
        t_axis = np.array([t - t0 for t in self.timestamps], dtype=np.float32)

        return spec_db, t_axis, v_axis_highres, centroid


def extract_gait_metrics(spec: np.ndarray, t_axis: np.ndarray, v_axis: np.ndarray) -> tuple[float, float, float]:
    """
    Computes gait statistics (Peak Velocity, Mean Absolute Velocity, SPM Cadence)
    from a fully processed spectrogram.
    """
    profile = spec.mean(axis=0)
    noise_floor = float(np.percentile(profile, 20))
    weights = np.maximum(profile - noise_floor, 0)
    w_sum = weights.sum()
    
    mean_abs = float((weights * np.abs(v_axis)).sum() / w_sum) if w_sum > 0 else 0.0
    peak_v = float(v_axis[int(np.argmax(profile))])

    spm = 0.0
    if len(t_axis) > 20:
        fps_est = len(t_axis) / float(t_axis[-1])
        nv = spec.shape[1]
        center_idx = nv // 2
        
        # Target kinetic energy in the moving bins only
        moving_bins = list(range(0, center_idx-2)) + list(range(center_idx+3, nv))
        movement = np.sum(spec[:, moving_bins], axis=1)
        
        movement = np.clip(movement, a_min=None, a_max=np.percentile(movement, 99.5))
        movement = (movement - np.mean(movement)) / (np.std(movement) + 1e-6)
        
        try:
            filtered_sig = butter_bandpass_filter(movement, 1.0, 4.0, fps_est)
            peaks, _ = find_peaks(filtered_sig, distance=int(fps_est / 4.0), prominence=0.4)
            
            total_steps = len(peaks)
            duration_min = float(t_axis[-1]) / 60.0
            if duration_min > 0:
                spm = total_steps / duration_min
        except Exception as e:
            log.warning(f"Cadence processing error: {e}")

    return peak_v, mean_abs, spm