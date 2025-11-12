"""
Feature Engineering for Weather Data
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import joblib
import logging
from pathlib import Path
from typing import Tuple, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeatherFeatureEngineer:
    """
    Engineer features from raw weather data for ML models
    Features Created: 40+ engineered features
    """
    
    def __init__(self, random_state: int = 42):
        """Initialize feature engineer"""
        self.scaler = StandardScaler()
        self.feature_names = None
        self.random_state = random_state
        logger.info("WeatherFeatureEngineer initialized")
    
    def load_data(self, csv_path: str) -> pd.DataFrame:
        """Load weather dataset with validation"""
        try:
            if not Path(csv_path).exists():
                raise FileNotFoundError(f"Data file not found: {csv_path}")
            
            df = pd.read_csv(csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            logger.info(f"✓ Loaded data: {df.shape[0]} rows × {df.shape[1]} columns")
            return df
        except Exception as e:
            logger.error(f"✗ Error loading data: {e}")
            raise
    
    def create_engineered_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create 40+ engineered features from raw weather data
        Categories:
        1. Temperature features
        2. Precipitation features
        3. Interaction features
        4. Wind features
        5. Time-based features
        6. Lag features
        7. Rolling features
        8. Seasonal features
        """
        df = df.copy()
        
        try:
            # ===== 1. TEMPERATURE FEATURES (8) =====
            df['temp_range'] = df['temperature_max'] - df['temperature_min']
            df['temp_deviation'] = abs(df['temperature_current'] - df['temperature_current'].mean())
            df['temp_above_20'] = (df['temperature_current'] > 20).astype(int)
            df['temp_below_15'] = (df['temperature_current'] < 15).astype(int)
            df['temp_optimal_growth'] = ((df['temperature_current'] > 15) & 
                                        (df['temperature_current'] < 35)).astype(int)
            df['gdd_normalized'] = df['temperature_growing_degree_days'] / 50.0
            df['temperature_stress_index'] = df['temperature_max'] - df['temperature_min']
            df['feels_like_index'] = df['temperature_current'] * 0.9  # Simplified
            
            # ===== 2. PRECIPITATION FEATURES (6) =====
            df['rain_intensity_ratio'] = df['precipitation_rain_3h'] / (df['precipitation_rain_1h'] + 0.01)
            df['has_light_rain'] = ((df['precipitation_rain_1h'] > 0) & 
                                   (df['precipitation_rain_1h'] <= 2.5)).astype(int)
            df['has_moderate_rain'] = ((df['precipitation_rain_1h'] > 2.5) & 
                                      (df['precipitation_rain_1h'] <= 10)).astype(int)
            df['has_heavy_rain'] = (df['precipitation_rain_1h'] > 10).astype(int)
            df['cumulative_rain_3h'] = df['precipitation_rain_1h'] + df['precipitation_rain_3h']
            df['rain_period'] = (df['extreme_weather_is_rainy']).astype(int)
            
            # ===== 3. HUMIDITY-TEMPERATURE INTERACTIONS (5) =====
            df['heat_humidity_stress'] = (df['temperature_current'] * df['humidity_relative_humidity']) / 1000
            df['dew_point_proxy'] = df['temperature_current'] - (100 - df['humidity_relative_humidity']) / 5
            df['moisture_stress'] = (100 - df['humidity_relative_humidity']) * df['temperature_current'] / 100
            df['comfort_index'] = 0.5 * df['temperature_current'] + 0.1 * df['humidity_relative_humidity']
            df['humidity_temp_product'] = df['humidity_relative_humidity'] * df['temperature_current'] / 100
            
            # ===== 4. WIND FEATURES (5) =====
            df['wind_stress_index'] = df['wind_speed'] * df['wind_gust'] / 10
            df['wind_turbulence'] = df['wind_gust'] - df['wind_speed']
            df['high_wind'] = (df['wind_speed'] > 5).astype(int)
            df['extreme_wind'] = (df['wind_speed'] > 10).astype(int)
            df['wind_pressure_index'] = df['wind_speed'] * df['humidity_pressure'] / 1000
            
            # ===== 5. TIME-BASED FEATURES (5) =====
            df['month'] = df['timestamp'].dt.month
            df['day_of_year'] = df['timestamp'].dt.dayofyear
            df['quarter'] = df['timestamp'].dt.quarter
            df['week_of_year'] = df['timestamp'].dt.isocalendar().week.astype(int)
            df['is_growing_season'] = ((df['month'] >= 4) & (df['month'] <= 9)).astype(int)
            
            # ===== 6. LAG FEATURES (9 - lag 1, 7, 30) =====
            for col in ['temperature_current', 'precipitation_rain_1h', 'humidity_relative_humidity']:
                df[f'{col}_lag1'] = df.groupby('region_name')[col].shift(1)
                df[f'{col}_lag7'] = df.groupby('region_name')[col].shift(7)
                df[f'{col}_lag30'] = df.groupby('region_name')[col].shift(30)
            
            # ===== 7. ROLLING FEATURES (12) =====
            for col in ['temperature_current', 'precipitation_rain_1h', 'wind_speed']:
                df[f'{col}_rolling_7d_mean'] = df.groupby('region_name')[col].transform(
                    lambda x: x.rolling(7, min_periods=1).mean()
                )
                df[f'{col}_rolling_30d_mean'] = df.groupby('region_name')[col].transform(
                    lambda x: x.rolling(30, min_periods=1).mean()
                )
                df[f'{col}_rolling_7d_std'] = df.groupby('region_name')[col].transform(
                    lambda x: x.rolling(7, min_periods=1).std()
                )
                df[f'{col}_rolling_30d_std'] = df.groupby('region_name')[col].transform(
                    lambda x: x.rolling(30, min_periods=1).std()
                )
            
            # ===== 8. CLOUD & RADIATION FEATURES (3) =====
            df['cloud_intensity'] = df['cloud_cover'] / 100.0
            df['clear_sky_index'] = 1 - (df['cloud_cover'] / 100.0)
            df['photosynthesis_potential'] = (1 - df['cloud_cover'] / 100.0) * (df['temperature_current'] / 30.0)
            
            # Fill NaN values from lag features
            df = df.fillna(df.mean(numeric_only=True))
            
            logger.info(f"✓ Created engineered features. Total: {df.shape[1]} columns")
            return df
            
        except Exception as e:
            logger.error(f"✗ Error in feature engineering: {e}")
            raise
    
    def select_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """
        Select best features for ML models
        Returns: (features), feature_names (list)
        """
        # Carefully selected features for agricultural prediction
        feature_cols = [
            # Core weather (8)
            'temperature_current', 'temperature_min', 'temperature_max',
            'humidity_relative_humidity', 'precipitation_rain_1h', 
            'wind_speed', 'cloud_cover', 'humidity_pressure',
            
            # Engineered temperature (8)
            'temp_range', 'gdd_normalized', 'temp_optimal_growth',
            'temperature_stress_index', 'temp_above_20', 'temp_below_15',
            'temp_deviation', 'temperature_growing_degree_days',
            
            # Engineered precipitation (4)
            'has_light_rain', 'has_moderate_rain', 'has_heavy_rain',
            'cumulative_rain_3h',
            
            # Interactions (4)
            'heat_humidity_stress', 'dew_point_proxy',
            'moisture_stress', 'humidity_temp_product',
            
            # Wind (3)
            'wind_stress_index', 'high_wind', 'extreme_wind',
            
            # Time (4)
            'month', 'quarter', 'day_of_year', 'is_growing_season',
            
            # Lags (6)
            'temperature_current_lag7', 'precipitation_rain_1h_lag7',
            'humidity_relative_humidity_lag7',
            'temperature_current_lag30', 'precipitation_rain_1h_lag30',
            'humidity_relative_humidity_lag30',
            
            # Rolling (6)
            'temperature_current_rolling_7d_mean', 'temperature_current_rolling_30d_mean',
            'precipitation_rain_1h_rolling_7d_mean', 'wind_speed_rolling_7d_mean',
            'temperature_current_rolling_7d_std', 'wind_speed_rolling_7d_std',
            
            # Cloud & radiation (2)
            'cloud_intensity', 'clear_sky_index',
            
            # Extreme weather (4)
            'extreme_weather_is_rainy', 'extreme_weather_is_thunderstorm',
            'extreme_weather_is_clear', 'extreme_weather_is_cloudy'
        ]
        
        # Keep only features that exist
        feature_cols = [col for col in feature_cols if col in df.columns]
        
        self.feature_names = feature_cols
        logger.info(f"Selected {len(feature_cols)} features for ML")
        
        return df[feature_cols], feature_cols
    
    def fit_scaler(self, X: pd.DataFrame) -> 'WeatherFeatureEngineer':
        """Fit StandardScaler on features"""
        try:
            self.scaler.fit(X)
            logger.info(f"Scaler fitted. Mean: {self.scaler.mean_.mean():.4f}, Std: {self.scaler.scale_.mean():.4f}")
            return self
        except Exception as e:
            logger.error(f"Error fitting scaler: {e}")
            raise
    
    def transform_features(self, X: pd.DataFrame) -> np.ndarray:
        """Transform features using fitted scaler"""
        try:
            X_scaled = self.scaler.transform(X)
            logger.info(f"Transformed features. Shape: {X_scaled.shape}")
            return X_scaled
        except Exception as e:
            logger.error(f"Error transforming features: {e}")
            raise
    
    def fit_transform(self, X: pd.DataFrame) -> np.ndarray:
        """Fit and transform in one step"""
        return self.fit_scaler(X).transform_features(X)
    
    def save_scaler(self, path: str = 'src/models/saved_models/scalers/feature_scaler.pkl') -> None:
        """Save fitted scaler for later use"""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self.scaler, path)
            logger.info(f"Scaler saved to {path}")
        except Exception as e:
            logger.error(f"Error saving scaler: {e}")
            raise
    
    def load_scaler(self, path: str = 'src/models/saved_models/scalers/feature_scaler.pkl') -> None:
        """Load fitted scaler"""
        try:
            if not Path(path).exists():
                raise FileNotFoundError(f"Scaler not found at {path}")
            self.scaler = joblib.load(path)
            logger.info(f"Scaler loaded from {path}")
        except Exception as e:
            logger.error(f"Error loading scaler: {e}")
            raise
    
    def get_feature_names(self) -> List[str]:
        """Get list of selected features"""
        return self.feature_names


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    
    print("=" * 80)
    print("WEATHER FEATURE ENGINEERING")
    print("=" * 80)
    
    # Initialize
    engineer = WeatherFeatureEngineer()
    
    # Load data
    df = engineer.load_data('data/raw/weather/all_regions_synthetic_weather_historical.csv')
    
    # Create engineered features
    df_engineered = engineer.create_engineered_features(df)
    print(f"\nEngineered features created: {df_engineered.shape[1]} total columns")
    
    # Select best features
    X, feature_names = engineer.select_features(df_engineered)
    print(f"Selected features: {len(feature_names)} features")
    print(f"  Sample features: {feature_names[:5]}")
    
    # Fit and transform scaler
    X_scaled = engineer.fit_transform(X)
    print(f"Scaled features: Mean={X_scaled.mean():.4f}, Std={X_scaled.std():.4f}")
    
    # Save scaler
    engineer.save_scaler()
    
    # Save processed data
    df_processed = df_engineered.copy()
    df_processed[X.columns] = X_scaled
    df_processed.to_csv('data/processed/weather_processed.csv', index=False)
    print(f"Processed data saved to data/processed/weather_processed.csv")
    
    print(f"\nFEATURE ENGINEERING COMPLETE!")
    print(f"=" * 80)
