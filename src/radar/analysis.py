import numpy as np
from scipy.signal import find_peaks, butter, filtfilt
import matplotlib.pyplot as plt

def analyze_gait_performance(time, velocity, velocity_scale_factor=2.0/15.0):
    """
    Analyzes radar micro-Doppler velocity data for a runner on a treadmill.
    """
    # 1. Data Calibration
    calibrated_velocity = velocity * velocity_scale_factor
    
    # Sampling frequency estimation
    dt = np.mean(np.diff(time))
    fs = 1.0 / dt
    
    # 2. Step Extraction (Swing Phase)
    # Expected running cadence: 2.5 to 3.5 Hz (150-210 SPM)
    # We look for positive peaks (forward foot swings)
    min_dist = int(fs / 4.0) # Approx 4 Hz max
    prominence = np.max(calibrated_velocity) * 0.2
    
    peaks, _ = find_peaks(calibrated_velocity, distance=min_dist, prominence=prominence)
    
    total_step_count = len(peaks)
    duration = time[-1] - time[0]
    avg_step_freq = total_step_count / duration if duration > 0 else 0
    spm = avg_step_freq * 60
    
    # 3. Drift & Correction Analysis (Center of Mass)
    # Low-pass filter to isolate torso movement (COM)
    # We want to remove the high-frequency leg swings
    try:
        b, a = butter(4, 0.8 / (fs / 2), btype='low')
        com_velocity = filtfilt(b, a, calibrated_velocity)
    except:
        com_velocity = calibrated_velocity # Fallback
        
    drift_threshold = -0.15  # m/s backward
    correction_threshold = 0.15 # m/s forward
    
    drifts = com_velocity < drift_threshold
    corrections = com_velocity > correction_threshold
    
    # 4. Gait Asymmetry Calculation
    # Assuming alternating peaks represent Left and Right legs
    # This is a common heuristic for treadmill running behind the runner
    left_peaks = peaks[0::2]
    right_peaks = peaks[1::2]
    
    # Amplitude Asymmetry
    left_amps = calibrated_velocity[left_peaks]
    right_amps = calibrated_velocity[right_peaks]
    
    amp_asymmetry = 0.0
    if len(left_amps) > 0 and len(right_amps) > 0:
        mean_l = np.mean(left_amps)
        mean_r = np.mean(right_amps)
        amp_asymmetry = (abs(mean_l - mean_r) / ((mean_l + mean_r) / 2)) * 100
        
    # Temporal Asymmetry
    # Mean difference in time gap (delta t) between L-to-R vs R-to-L
    # L->R gaps: p[1]-p[0], p[3]-p[2]...
    # R->L gaps: p[2]-p[1], p[4]-p[3]...
    gaps_lr = []
    gaps_rl = []
    
    # We need at least 3 peaks for full cycle comparison
    for i in range(len(peaks) - 1):
        gap = time[peaks[i+1]] - time[peaks[i]]
        if i % 2 == 0:
            gaps_lr.append(gap)
        else:
            gaps_rl.append(gap)
            
    temp_asymmetry = 0.0
    if len(gaps_lr) > 0 and len(gaps_rl) > 0:
        # We compare the means of the gaps
        temp_asymmetry = abs(np.mean(gaps_lr) - np.mean(gaps_rl))

    return {
        "time": time,
        "raw_velocity": velocity,
        "calibrated_velocity": calibrated_velocity,
        "com_velocity": com_velocity,
        "peaks": peaks,
        "left_peaks": left_peaks,
        "right_peaks": right_peaks,
        "drifts": drifts,
        "corrections": corrections,
        "total_step_count": total_step_count,
        "avg_step_freq": avg_step_freq,
        "spm": spm,
        "amp_asymmetry": amp_asymmetry,
        "temp_asymmetry": temp_asymmetry
    }

def plot_gait_analysis(results):
    """
    Generates the stacked multi-plot figure.
    """
    time = results["time"]
    v_cal = results["calibrated_velocity"]
    com = results["com_velocity"]
    peaks = results["peaks"]
    drifts = results["drifts"]
    corrections = results["corrections"]
    l_peaks = results["left_peaks"]
    r_peaks = results["right_peaks"]
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12), sharex=False)
    
    # Plot 1: Calibrated raw signal with markers on detected steps
    ax1.plot(time, v_cal, label="Calibrated Velocity", color="gray", alpha=0.5)
    ax1.scatter(time[peaks], v_cal[peaks], color="red", label="Detected Steps", zorder=3)
    ax1.set_title("Calibrated Radar Velocity & Step Detection")
    ax1.set_ylabel("Velocity (m/s)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Isolated COM signal with Drift and Correction zones
    ax2.plot(time, com, color="blue", label="Center of Mass (Torso)")
    
    # Shading drift and correction
    ax2.fill_between(time, min(com), max(com), where=drifts, color='red', alpha=0.2, label="Drift (Backward)")
    ax2.fill_between(time, min(com), max(com), where=corrections, color='green', alpha=0.2, label="Correction (Forward)")
    
    ax2.axhline(0, color='black', linestyle='--', alpha=0.5)
    ax2.set_title("Center of Mass Drift & Correction Analysis")
    ax2.set_ylabel("Velocity (m/s)")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Left vs Right comparison
    l_amps = v_cal[l_peaks]
    r_amps = v_cal[r_peaks]
    
    # Stem plot comparison
    ax3.stem(time[l_peaks], l_amps, linefmt='C0-', markerfmt='C0o', label='Left Leg')
    ax3.stem(time[r_peaks], r_amps, linefmt='C1-', markerfmt='C1o', label='Right Leg')
    
    ax3.set_title(f"Gait Asymmetry: Amp={results['amp_asymmetry']:.1f}%, Temp={results['temp_asymmetry']:.3f}s")
    ax3.set_xlabel("Time (s)")
    ax3.set_ylabel("Peak Velocity (m/s)")
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig
