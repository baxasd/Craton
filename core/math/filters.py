import pandas as pd
import numpy as np

# Pulls our central logic that knows how to find joint columns (e.g., 'j0_x')
from core.io.structs import identify_joint_columns

class PipelineProcessor:
    """
    Digital Signal Processing (DSP) for 3D Motion Data.
    Cleans up AI hallucinations, fills in missing gaps, and smooths micro-jitters.
    """

    @staticmethod
    def _get_all_joint_cols(df: pd.DataFrame) -> list:
        """
        Helper Function: DRY (Don't Repeat Yourself) Optimization.
        Scans the DataFrame and returns a safe list of all X, Y, and Z columns 
        that actually exist in the current file.
        """
        x_cols = identify_joint_columns(df.columns)
        all_cols = []
        for c in x_cols:
            base = c[:-2] # Strips '_x' to get the base name (e.g., 'j0')
            all_cols.extend([f"{base}_x", f"{base}_y", f"{base}_z"])
            
        # Return only the columns that actually exist in the DataFrame to prevent KeyErrors
        return [c for c in all_cols if c in df.columns]

    @staticmethod
    def validate(df: pd.DataFrame):
        """
        Scans the DataFrame for obvious errors before we run heavy math on it.
        Returns: (report_string, needs_repair_bool)
        """
        report = []
        issues = 0
        
        # 1. Structural Check
        x_cols = identify_joint_columns(df.columns)
        if not x_cols:
            return "CRITICAL: No joint data found (checked for 'j0_x' format).", False
            
        existing_cols = PipelineProcessor._get_all_joint_cols(df)
        
        # 2. Tracking Loss Check (MediaPipe often defaults to exactly 0.0 when it fails to see a limb)
        zeros = (df[existing_cols] == 0.0).sum().sum()
        if zeros > 0:
            pct = (zeros / df[existing_cols].size) * 100
            report.append(f"• Tracking Loss: {pct:.1f}% zeros detected.")
            issues += 1
            
        # 3. Gap Check (Null/NaN values)
        nans = df[existing_cols].isna().sum().sum()
        if nans > 0:
            report.append(f"• Data Gaps: {nans} missing values.")
            issues += 1

        # 4. Frame Drop Check (Did the camera lag and skip frames?)
        if 'frame' in df.columns:
            diffs = df['frame'].diff().fillna(1)
            drops = (diffs > 1).sum()
            if drops > 0:
                report.append(f"• Frame Drops: {int(drops)} discontinuities detected.")
                issues += 1

        if issues == 0:
            return "DATA INTEGRITY: PASS", False
        else:
            header = f"ISSUES FOUND ({issues}):"
            return header + "\n" + "\n".join(report), True

    @staticmethod
    def remove_teleportation(df: pd.DataFrame, threshold=0.5):
        """
        Removes impossible physical movements.
        If a knee is at X=1.0m, and in the very next frame (0.03 seconds later) 
        it is at X=3.0m, it "teleported". We nullify that frame so it can be interpolated.
        """
        df_clean = df.copy()
        x_cols = identify_joint_columns(df_clean.columns)
        
        teleports_found = 0
        
        # Loop through each joint individually
        for c in x_cols:
            base = c[:-2]
            cols = [f"{base}_x", f"{base}_y", f"{base}_z"]
            
            if not all(k in df_clean.columns for k in cols): continue
            
            # Calculate distance moved since the previous frame using fast Pandas diff()
            diffs = df_clean[cols].diff()
            
            # 3D Euclidean distance equation: sqrt(x^2 + y^2 + z^2)
            dists = np.sqrt((diffs**2).sum(axis=1))
            
            # Create a boolean mask of rows where the distance exceeded our physical threshold (e.g. 0.5 meters)
            jump_idx = dists > threshold
            teleports_found += jump_idx.sum()
            
            # Nullify those impossible coordinates (Turn them into NaNs)
            df_clean.loc[jump_idx, cols] = np.nan
            
        return df_clean, teleports_found

    @staticmethod
    def repair(df: pd.DataFrame, method='linear', limit=30):
        """
        Fills in the gaps (NaNs and 0.0s) created by dropped frames or teleportation.
        Uses Pandas interpolation to draw a line between the last known good points.
        """
        df_clean = df.copy()
        valid_cols = PipelineProcessor._get_all_joint_cols(df_clean)
        
        # Convert exact zeros to NaN so the interpolator recognizes them as "missing" data
        df_clean[valid_cols] = df_clean[valid_cols].replace(0.0, np.nan)
        
        # Connect the dots
        try:
            if method == 'spline':
                # Spline creates natural curves, but can sometimes overshoot if the gap is too large
                df_clean[valid_cols] = df_clean[valid_cols].interpolate(method='spline', order=3, limit=limit, limit_direction='both')
            else:
                # Linear draws a straight line. Safest method for noisy data.
                df_clean[valid_cols] = df_clean[valid_cols].interpolate(method='linear', limit=limit, limit_direction='both')
        except:
            # Fallback if strict limit_direction fails
            df_clean[valid_cols] = df_clean[valid_cols].interpolate(method='linear', limit=limit)
            
        # If there are still NaNs left (e.g., at the very start of the file), force them to 0.0 so math won't crash
        return df_clean.fillna(0.0)

    @staticmethod
    def smooth(df: pd.DataFrame, window=5):
        """
        Applies a Moving Average filter to smooth out micro-jitters in the AI tracking.
        'window' represents how many frames to average together.
        """
        df_proc = df.copy()
        valid_cols = PipelineProcessor._get_all_joint_cols(df_proc)
            
        if valid_cols:
            # center=True ensures the moving average doesn't mathematically "delay" or shift the movements backward in time
            df_proc[valid_cols] = df_proc[valid_cols].rolling(window=window, min_periods=1, center=True).mean()
            
        return df_proc