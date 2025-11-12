"""
Configuration Management for Weather Module
===========================================
Centralized configuration for paths, hyperparameters, and settings
"""

from pathlib import Path
from typing import Dict, Any
import json


class Config:
    """Centralized configuration management"""
    
    # ===== PATHS =====
    PROJECT_ROOT = Path(__file__).parent.parent
    DATA_RAW = PROJECT_ROOT / 'data' / 'raw'
    DATA_PROCESSED = PROJECT_ROOT / 'data' / 'processed'
    MODELS_DIR = PROJECT_ROOT / 'src' / 'models' / 'saved_models'
    WEATHER_DATA_RAW = DATA_RAW / 'weather'
    WEATHER_MODELS_DIR = MODELS_DIR / 'weather_models'
    SCALERS_DIR = MODELS_DIR / 'scalers'
    NOTEBOOKS_DIR = PROJECT_ROOT / 'notebooks'
    DOCS_DIR = PROJECT_ROOT / 'docs'
    
    # ===== DATA PATHS =====
    WEATHER_RAW_CSV = WEATHER_DATA_RAW / 'all_regions_synthetic_weather_historical.csv'
    WEATHER_PROCESSED_CSV = DATA_PROCESSED / 'weather_processed.csv'
    BASELINE_RESULTS_CSV = DATA_PROCESSED / 'baseline_results.csv'
    FEATURE_SCALER_PATH = SCALERS_DIR / 'feature_scaler.pkl'
    MODEL_REGISTRY_PATH = MODELS_DIR / 'model_registry.json'
    
    # ===== MODEL PATHS =====
    LINEAR_REGRESSION_PATH = WEATHER_MODELS_DIR / 'linear_regression_weather.pkl'
    RANDOM_FOREST_PATH = WEATHER_MODELS_DIR / 'random_forest_weather.pkl'
    SVR_PATH = WEATHER_MODELS_DIR / 'svr_weather.pkl'
    
    # ===== HYPERPARAMETERS =====
    RANDOM_STATE = 42
    TEST_SIZE = 0.2
    CV_FOLDS = 5
    
    # ===== RANDOM FOREST PARAMS =====
    RF_N_ESTIMATORS = 100
    RF_MAX_DEPTH = 10
    RF_N_JOBS = -1
    
    # ===== SVR PARAMS =====
    SVR_KERNEL = 'rbf'
    SVR_C = 100
    SVR_EPSILON = 0.1
    SVR_GAMMA = 'scale'
    
    # ===== FEATURE ENGINEERING =====
    FEATURE_SCALER_TYPE = 'StandardScaler'
    
    # ===== WEATHER DATA REGIONS =====
    AGRICULTURAL_REGIONS = [
        'Delhi NCR',
        'Punjab',
        'Haryana',
        'Maharashtra',
        'Karnataka',
        'Tamil Nadu',
        'West Bengal',
        'Madhya Pradesh'
    ]
    
    @classmethod
    def create_directories(cls) -> None:
        """Create all necessary directories"""
        dirs = [
            cls.DATA_RAW,
            cls.DATA_PROCESSED,
            cls.WEATHER_MODELS_DIR,
            cls.SCALERS_DIR,
            cls.NOTEBOOKS_DIR,
            cls.DOCS_DIR
        ]
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return {
            'paths': {
                'project_root': str(cls.PROJECT_ROOT),
                'data_raw': str(cls.DATA_RAW),
                'data_processed': str(cls.DATA_PROCESSED),
                'models': str(cls.MODELS_DIR),
            },
            'hyperparameters': {
                'random_state': cls.RANDOM_STATE,
                'test_size': cls.TEST_SIZE,
                'cv_folds': cls.CV_FOLDS,
            },
            'regions': cls.AGRICULTURAL_REGIONS
        }
    
    @classmethod
    def print_config(cls) -> None:
        """Print current configuration"""
        print("\n" + "=" * 80)
        print("⚙️  CONFIGURATION")
        print("=" * 80)
        
        print("\n📁 PATHS:")
        print(f"  Project Root: {cls.PROJECT_ROOT}")
        print(f"  Data Raw: {cls.DATA_RAW}")
        print(f"  Data Processed: {cls.DATA_PROCESSED}")
        print(f"  Models: {cls.MODELS_DIR}")
        
        print("\n🔧 HYPERPARAMETERS:")
        print(f"  Random State: {cls.RANDOM_STATE}")
        print(f"  Test Size: {cls.TEST_SIZE}")
        print(f"  CV Folds: {cls.CV_FOLDS}")
        
        print("\n🌾 REGIONS:")
        for region in cls.AGRICULTURAL_REGIONS:
            print(f"  - {region}")
        
        print("\n" + "=" * 80)


if __name__ == "__main__":
    Config.create_directories()
    Config.print_config()
