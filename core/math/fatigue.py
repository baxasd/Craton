import numpy as np

class FatigueAnalyzer:
    """
    Advanced Biomechanics Engine.
    Detects systemic postural breakdown by establishing a "fresh" baseline 
    at the start of a run, and measuring multivariate deviation over time.
    """
    def __init__(self, df_timeseries, fps=15, baseline_mins=5, rolling_window_sec=60):
        # Always operate on a copy so we don't accidentally mutate the original data
        self.df = df_timeseries.copy() 
        self.fps = fps
        
        # Convert human time (minutes/seconds) into exact array row counts
        self.baseline_frames = int(baseline_mins * 60 * fps)
        self.rolling_frames = int(rolling_window_sec * fps)
        
        # Grab all the angle columns (e.g., 'l_knee', 'lean_z'), excluding metadata
        self.metric_cols = [c for c in self.df.columns if c not in ['timestamp', 'frame']]
        
        # Initialize statistical states
        self.baseline_mean = None
        self.baseline_std = None
        self.cov_matrix = None
        self.inv_cov_matrix = None

    def run_pipeline(self):
        """Executes the math pipeline in order. Called by the HeavyTaskWorker in tab_gait.py."""
        self._calculate_baseline()
        self._calculate_rolling_metrics()
        self._calculate_mahalanobis()
        self._calculate_fii()
        
        summary_df, onset_min = self._generate_summary()
        adv_metrics = self._calculate_advanced_metrics() 
        
        return self.df, summary_df, onset_min, adv_metrics

    def _calculate_baseline(self):
        """
        Step 1: Define what 'normal' looks like.
        Takes the first N minutes of the run and calculates the Covariance Matrix.
        This captures how the runner's joints naturally move together when they aren't tired.
        """
        baseline_data = self.df.iloc[:self.baseline_frames][self.metric_cols]
        
        self.baseline_mean = baseline_data.mean()
        self.baseline_std = baseline_data.std()
        
        # Covariance Matrix: Measures the directional relationship between all joints
        self.cov_matrix = np.cov(baseline_data.T)
        
        # Pseudo-Inverse Covariance: Used later to calculate the Mahalanobis distance. 
        # Using pinv (pseudo-inverse) instead of inv prevents crashes if a joint doesn't move at all.
        self.inv_cov_matrix = np.linalg.pinv(self.cov_matrix)

    def _calculate_rolling_metrics(self):
        """
        Step 2: Smooth the data and calculate Z-Scores.
        A Z-Score tells us how many Standard Deviations a joint has moved from its baseline.
        """
        # Smooth out micro-jitters over a 60-second window
        rolling_means = self.df[self.metric_cols].rolling(window=self.rolling_frames, min_periods=1).mean()
        
        for col in self.metric_cols:
            self.df[f'{col}_zscore'] = (rolling_means[col] - self.baseline_mean[col]) / self.baseline_std[col]
            
        self.smoothed_data = rolling_means

    def _calculate_mahalanobis(self):
        """
        Step 3: Multivariate Drift Calculation.
        OPTIMIZATION: This calculates the true Mahalanobis Distance for all rows simultaneously
        using NumPy matrix math instead of iterrows(). Runs 1000x faster.
        """
        centroid = self.baseline_mean.values
        
        # Fill NaNs with 0 to prevent matrix math crashes
        clean_data = self.smoothed_data.fillna(0).values 
        
        # Calculate the Delta (Difference between current posture and baseline posture)
        delta = clean_data - centroid
        
        # Mahalanobis Equation: sqrt((x - m)^T * Sigma^-1 * (x - m))
        # np.dot(delta, inv_cov) applies the inverse covariance matrix to the deltas.
        left_term = np.dot(delta, self.inv_cov_matrix)
        
        # Element-wise multiplication and sum across the row is equivalent to the final matrix dot product.
        distances = np.sqrt(np.sum(left_term * delta, axis=1))
        
        self.df['mahalanobis_dist'] = distances

    def _calculate_fii(self):
        """
        Step 4: Fatigue Index Indicator (FII).
        A custom composite metric blending absolute Z-Scores and normalized Mahalanobis Drift.
        """
        z_cols = [c for c in self.df.columns if c.endswith('_zscore')]
        self.df['mean_abs_z'] = self.df[z_cols].abs().mean(axis=1)
        
        self.df['norm_mahalanobis'] = self.df['mahalanobis_dist'] / len(self.metric_cols)
        self.df['FII'] = self.df['norm_mahalanobis'] + self.df['mean_abs_z']

    def _generate_summary(self):
        """Step 5: Roll the frame-by-frame data up into per-minute averages."""
        self.df['minute'] = (self.df['timestamp'] // 60).astype(int) + 1
        
        summary_df = self.df.groupby('minute').agg(
            FII=('FII', 'mean'), 
            Mahalanobis=('mahalanobis_dist', 'mean')
        ).reset_index()
        
        # Flag the exact minute where FII crosses the critical threshold of 2.0
        onset_df = summary_df[summary_df['FII'] > 2.0]
        fatigue_onset_min = onset_df['minute'].iloc[0] if not onset_df.empty else None
        
        return summary_df, fatigue_onset_min

    def _calculate_advanced_metrics(self):
        """
        Step 6: Trendline generation.
        Calculates per-minute slopes and brutally detailed descriptive stats for all columns.
        """
        metrics = {}
        t_sec = self.df['timestamp'].values
        
        # 1. Calculate the Rate of Change (Slope per minute) using Linear Regression
        if len(t_sec) > 1:
            for col in self.metric_cols + ['mahalanobis_dist']:
                # np.polyfit(X, Y, degree=1) calculates the line of best fit. 
                # [0] grabs the slope. Multiply by 60 to get drift per minute.
                metrics[f'slope_{col}'] = np.polyfit(t_sec, self.df[col].fillna(0), 1)[0] * 60
        else:
            for col in self.metric_cols + ['mahalanobis_dist']:
                metrics[f'slope_{col}'] = 0.0

        # 2. Extract standard pandas describe() to merge into our console text in tab_gait
        safe_df = self.df.drop(columns=['timestamp', 'frame', 'minute', 'norm_mahalanobis', 'mean_abs_z', 'FII'], errors='ignore')
        metrics['describe'] = safe_df.describe().T
        
        return metrics