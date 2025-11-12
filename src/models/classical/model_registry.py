"""
Model Registry - Track and Manage All Trained Models
====================================================
Essential for:
- Recording model metadata
- Tracking performance metrics
- Enabling model versioning
- Supporting model selection
"""

import json
import joblib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Central registry for all trained models
    
    Tracks:
    - Model name, type, and location
    - Training metrics and metadata
    - Creation timestamps
    - Model status (active, deprecated, etc.)
    """
    
    def __init__(self, registry_path: str = 'src/models/saved_models/model_registry.json'):
        """Initialize model registry"""
        self.registry_path = registry_path
        self.registry: Dict[str, Dict[str, Any]] = self.load_registry()
        logger.info(f"ModelRegistry initialized. Path: {registry_path}")
    
    def load_registry(self) -> Dict[str, Dict[str, Any]]:
        """Load existing registry from JSON"""
        if Path(self.registry_path).exists():
            try:
                with open(self.registry_path, 'r') as f:
                    registry = json.load(f)
                logger.info(f"Loaded existing registry with {len(registry)} models")
                return registry
            except Exception as e:
                logger.error(f"Error loading registry: {e}")
                return {}
        return {}
    
    def register_model(self, 
                      model_name: str, 
                      model_type: str,
                      metrics: Dict[str, Any],
                      model_path: str,
                      dataset: str = 'weather',
                      description: str = '') -> None:
        """
        Register a trained model with metadata
        
        Args:
            model_name: Unique identifier for model
            model_type: Type of model (RandomForestRegressor, etc.)
            metrics: Performance metrics dict
            model_path: Path where model is saved
            dataset: Dataset used for training
            description: Human-readable description
        """
        try:
            self.registry[model_name] = {
                'name': model_name,
                'type': model_type,
                'dataset': dataset,
                'path': model_path,
                'metrics': metrics,
                'created_at': datetime.now().isoformat(),
                'description': description,
                'status': 'active'
            }
            
            self.save_registry()
            logger.info(f"Registered new model: {model_name}")
            
        except Exception as e:
            logger.error(f"Error registering model: {e}")
            raise
    
    def save_registry(self) -> None:
        """Persist registry to disk"""
        try:
            Path(self.registry_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_path, 'w') as f:
                json.dump(self.registry, f, indent=2)
            logger.info(f"✓ Registry saved to {self.registry_path}")
        except Exception as e:
            logger.error(f"Error saving registry: {e}")
            raise
    
    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific model"""
        return self.registry.get(model_name)
    
    def list_models(self, dataset: Optional[str] = None, 
                   status: str = 'active') -> Dict[str, Dict[str, Any]]:
        """
        List models, optionally filtered
        
        Args:
            dataset: Filter by dataset name
            status: Filter by status
        """
        result = {}
        for name, info in self.registry.items():
            if status and info.get('status') != status:
                continue
            if dataset and info.get('dataset') != dataset:
                continue
            result[name] = info
        
        logger.info(f"✓ Found {len(result)} models matching criteria")
        return result
    
    def get_best_model(self, dataset: str, metric: str = 'test_mse') -> tuple:
        """
        Get best model for a dataset by metric
        
        Returns: (model_name, model_info)
        """
        models = self.list_models(dataset=dataset)
        
        if not models:
            logger.warning(f"⚠ No models found for dataset: {dataset}")
            return None, None
        
        # Find model with best metric
        best_model = min(
            models.items(),
            key=lambda x: x[1]['metrics'].get(metric, float('inf'))
        )
        
        logger.info(f"✓ Best model: {best_model[0]} ({metric}={best_model[1]['metrics'].get(metric)})")
        return best_model
    
    def get_model(self, model_name: str):
        """Load and return a trained model"""
        try:
            model_info = self.get_model_info(model_name)
            if not model_info:
                raise ValueError(f"Model not found: {model_name}")
            
            model_path = model_info['path']
            if not Path(model_path).exists():
                raise FileNotFoundError(f"Model file not found: {model_path}")
            
            model = joblib.load(model_path)
            logger.info(f"✓ Loaded model: {model_name} from {model_path}")
            return model
            
        except Exception as e:
            logger.error(f"✗ Error loading model: {e}")
            raise
    
    def print_registry(self) -> None:
        """Pretty print registry contents"""
        logger.info("\n" + "=" * 80)
        logger.info("📚 MODEL REGISTRY")
        logger.info("=" * 80)
        
        if not self.registry:
            logger.info("No models registered yet")
            return
        
        for name, info in self.registry.items():
            logger.info(f"\n📌 {name}")
            logger.info(f"   Type: {info['type']}")
            logger.info(f"   Dataset: {info['dataset']}")
            logger.info(f"   Path: {info['path']}")
            logger.info(f"   Created: {info['created_at']}")
            logger.info(f"   Status: {info['status']}")
            if info.get('metrics'):
                metrics = info['metrics']
                logger.info(f"   Metrics: MSE={metrics.get('test_mse', 'N/A'):.4f}, R²={metrics.get('test_r2', 'N/A'):.4f}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of registry"""
        datasets = set()
        model_types = set()
        
        for info in self.registry.values():
            datasets.add(info.get('dataset'))
            model_types.add(info.get('type'))
        
        return {
            'total_models': len(self.registry),
            'datasets': list(datasets),
            'model_types': list(model_types),
            'registered_at': datetime.now().isoformat()
        }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    
    # Create registry
    registry = ModelRegistry()
    
    # Example: Register weather models
    registry.register_model(
        'weather_random_forest_v1',
        'RandomForestRegressor',
        {
            'train_mse': 2.34,
            'test_mse': 3.12,
            'train_r2': 0.95,
            'test_r2': 0.93,
            'cv_mse': 3.05
        },
        'src/models/saved_models/weather_models/random_forest_weather.pkl',
        dataset='weather',
        description='Random Forest baseline for weather-based yield prediction'
    )
    
    registry.register_model(
        'weather_svr_v1',
        'SVR',
        {
            'train_mse': 8.45,
            'test_mse': 9.23,
            'train_r2': 0.78,
            'test_r2': 0.76,
            'cv_mse': 9.15
        },
        'src/models/saved_models/weather_models/svr_weather.pkl',
        dataset='weather',
        description='SVR baseline for weather-based yield prediction'
    )
    
    registry.register_model(
        'weather_linear_v1',
        'LinearRegression',
        {
            'train_mse': 15.23,
            'test_mse': 15.89,
            'train_r2': 0.65,
            'test_r2': 0.63,
            'cv_mse': 15.75
        },
        'src/models/saved_models/weather_models/linear_regression_weather.pkl',
        dataset='weather',
        description='Linear Regression baseline for weather-based yield prediction'
    )
    
    # Print registry
    registry.print_registry()
    
    # List weather models
    weather_models = registry.list_models(dataset='weather')
    print(f"\n✓ Weather models: {list(weather_models.keys())}")
    
    # Get best model
    best_name, best_info = registry.get_best_model('weather', metric='test_mse')
    print(f"\n✓ Best weather model: {best_name}")
    print(f"   Test MSE: {best_info['metrics']['test_mse']:.4f}")
    
    # Get summary
    summary = registry.get_summary()
    print(f"\n📊 Registry Summary: {summary}")
