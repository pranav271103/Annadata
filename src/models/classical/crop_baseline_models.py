"""
Crop Baseline Models
====================
Train classical ML models on engineered crop features
Compare to weather baseline (MSE: 38.20)

File Location: src/models/classical/crop_baseline_models.py
Input: data/processed/crop_processed.csv (19,689 × 37)
Target: Yield (real values, 0 to 21,105)
Output: 3 trained models + results CSV + updated registry
"""

import pandas as pd
import numpy as np
import joblib
import logging
import json
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.svm import SVR
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CropBaselines:
    """Train classical ML baselines on real crop data"""
    
    def __init__(self, random_state=42):
        """Initialize baseline trainer"""
        self.models = {
            'linear_regression': LinearRegression(),
            'random_forest': RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=random_state,
                n_jobs=-1
            ),
            'svr': SVR(kernel='rbf', C=100, epsilon=0.1, gamma='scale')
        }
        self.trained_models = {}
        self.results = {}
        self.random_state = random_state
        logger.info("✓ CropBaselines initialized")
    
    def load_data(self, csv_path='data/processed/crop_processed.csv'):
        """Load engineered crop features"""
        try:
            if not Path(csv_path).exists():
                raise FileNotFoundError(f"Data not found: {csv_path}")
            
            df = pd.read_csv(csv_path)
            logger.info(f"✓ Loaded crop data: {df.shape[0]} rows × {df.shape[1]} columns")
            return df
        except Exception as e:
            logger.error(f"✗ Error loading data: {e}")
            raise
    
    def load_raw_yield(self, raw_csv='data/processed/crop_raw_data.csv'):
        """Load yield target from raw data"""
        try:
            raw_df = pd.read_csv(raw_csv)
            yield_values = raw_df['Yield'].values
            logger.info(f"✓ Loaded yield target: {len(yield_values)} values")
            return yield_values
        except Exception as e:
            logger.error(f"✗ Error loading yield: {e}")
            raise
    
    def prepare_data(self, X, y, test_size=0.2):
        """Prepare train/test split"""
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=self.random_state
            )
            
            logger.info(f"\n📊 Dataset Split:")
            logger.info(f"   Training: {X_train.shape[0]} samples")
            logger.info(f"   Testing: {X_test.shape[0]} samples")
            logger.info(f"   Features: {X_train.shape[1]}")
            logger.info(f"   Target range: {y.min():.2f} - {y.max():.2f}")
            
            return X_train, X_test, y_train, y_test
        except Exception as e:
            logger.error(f"✗ Error preparing data: {e}")
            raise
    
    def train_and_evaluate(self, X_train, X_test, y_train, y_test):
        """Train all models with evaluation"""
        try:
            for model_name, model in self.models.items():
                logger.info(f"\n🔄 Training {model_name.upper()}...")
                
                # Train
                model.fit(X_train, y_train)
                self.trained_models[model_name] = model
                
                # Predictions
                y_train_pred = model.predict(X_train)
                y_test_pred = model.predict(X_test)
                
                # Metrics
                train_mse = mean_squared_error(y_train, y_train_pred)
                test_mse = mean_squared_error(y_test, y_test_pred)
                train_r2 = r2_score(y_train, y_train_pred)
                test_r2 = r2_score(y_test, y_test_pred)
                train_mae = mean_absolute_error(y_train, y_train_pred)
                test_mae = mean_absolute_error(y_test, y_test_pred)
                
                # Cross-validation
                cv_scores = cross_val_score(
                    model, X_train, y_train,
                    cv=5,
                    scoring='neg_mean_squared_error'
                )
                cv_mse = -cv_scores.mean()
                cv_std = cv_scores.std()
                
                self.results[model_name] = {
                    'train_mse': train_mse,
                    'test_mse': test_mse,
                    'train_r2': train_r2,
                    'test_r2': test_r2,
                    'train_mae': train_mae,
                    'test_mae': test_mae,
                    'cv_mse': cv_mse,
                    'cv_std': cv_std
                }
                
                logger.info(f"   ✓ Train MSE: {train_mse:.4f} | Test MSE: {test_mse:.4f}")
                logger.info(f"   ✓ Train R²: {train_r2:.4f} | Test R²: {test_r2:.4f}")
                logger.info(f"   ✓ CV MSE: {cv_mse:.4f} (±{cv_std:.4f})")
        except Exception as e:
            logger.error(f"✗ Error in training: {e}")
            raise
    
    def save_models(self, save_dir='src/models/saved_models/crop_models'):
        """Save trained models"""
        try:
            Path(save_dir).mkdir(parents=True, exist_ok=True)
            
            for model_name, model in self.trained_models.items():
                path = f"{save_dir}/{model_name}_crop.pkl"
                joblib.dump(model, path)
                logger.info(f"✓ Saved {model_name}: {path}")
        except Exception as e:
            logger.error(f"✗ Error saving models: {e}")
            raise
    
    def get_results_dataframe(self):
        """Convert results to DataFrame"""
        return pd.DataFrame({
            'Model': list(self.results.keys()),
            'Train MSE': [r['train_mse'] for r in self.results.values()],
            'Test MSE': [r['test_mse'] for r in self.results.values()],
            'CV MSE': [r['cv_mse'] for r in self.results.values()],
            'Train R²': [r['train_r2'] for r in self.results.values()],
            'Test R²': [r['test_r2'] for r in self.results.values()],
            'Train MAE': [r['train_mae'] for r in self.results.values()],
            'Test MAE': [r['test_mae'] for r in self.results.values()],
            'CV Std': [r['cv_std'] for r in self.results.values()],
        })
    
    def print_summary(self):
        """Print results summary"""
        logger.info("\n" + "=" * 80)
        logger.info("📊 CROP MODEL PERFORMANCE SUMMARY")
        logger.info("=" * 80)
        
        results_df = self.get_results_dataframe()
        results_df = results_df.sort_values('Test MSE').reset_index(drop=True)
        
        logger.info("\nRanked by Test MSE (Lower is Better):\n")
        for idx, row in results_df.iterrows():
            logger.info(f"{idx+1}. {row['Model'].upper()}")
            logger.info(f"   Test MSE: {row['Test MSE']:.4f} | Test R²: {row['Test R²']:.4f}")
        
        best_model = results_df.iloc[0]['Model']
        best_mse = results_df.iloc[0]['Test MSE']
        best_r2 = results_df.iloc[0]['Test R²']
        
        logger.info(f"\n✅ BEST CROP MODEL: {best_model}")
        logger.info(f"   Test MSE: {best_mse:.4f}")
        logger.info(f"   Test R²: {best_r2:.4f}")
        
        # Compare to weather baseline
        weather_baseline_mse = 38.20
        logger.info(f"\n📊 COMPARISON TO WEATHER BASELINE:")
        logger.info(f"   Weather MSE: 38.20")
        logger.info(f"   Crop MSE: {best_mse:.4f}")
        
        if best_mse < weather_baseline_mse:
            improvement = ((weather_baseline_mse - best_mse) / weather_baseline_mse) * 100
            logger.info(f"   ✅ CROP BETTER! Improvement: {improvement:.1f}%")
        else:
            diff = ((best_mse - weather_baseline_mse) / weather_baseline_mse) * 100
            logger.info(f"   ⚠️ Weather better by {diff:.1f}%")
        
        logger.info(f"\n💡 R² ANALYSIS:")
        logger.info(f"   Weather R²: 0.08 (synthetic data)")
        logger.info(f"   Crop R²: {best_r2:.4f} (REAL data!)")
        logger.info(f"   → Crop model has {best_r2*100/0.08:.0f}× better fit!")
        
        return results_df
    
    def export_results(self, output_path='data/processed/crop_baseline_results.csv'):
        """Export results to CSV"""
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            results_df = self.get_results_dataframe()
            results_df.to_csv(output_path, index=False)
            logger.info(f"✓ Results exported: {output_path}")
            return results_df
        except Exception as e:
            logger.error(f"✗ Error exporting results: {e}")
            raise
    
    def update_registry(self, registry_path='src/models/saved_models/model_registry.json'):
        """Update model registry with crop models"""
        try:
            Path(registry_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Load existing registry
            if Path(registry_path).exists():
                with open(registry_path, 'r') as f:
                    registry = json.load(f)
            else:
                registry = {}
            
            # Add crop models
            for model_name, metrics in self.results.items():
                registry[f'crop_{model_name}_v1'] = {
                    'type': model_name,
                    'dataset': 'crop',
                    'path': f'src/models/saved_models/crop_models/{model_name}_crop.pkl',
                    'metrics': {k: float(v) for k, v in metrics.items()},
                    'created_at': pd.Timestamp.now().isoformat(),
                    'status': 'active'
                }
            
            with open(registry_path, 'w') as f:
                json.dump(registry, f, indent=2)
            
            logger.info(f"✓ Model registry updated: {registry_path}")
            logger.info(f"   Total models now in registry: {len(registry)}")
        except Exception as e:
            logger.error(f"✗ Error updating registry: {e}")
            raise


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    
    print("\n" + "=" * 80)
    print("🌾 CROP-BASED CLASSICAL ML BASELINES")
    print("=" * 80)
    
    try:
        # Initialize
        logger.info("\n🚀 Initializing crop baseline trainer...")
        baseline = CropBaselines(random_state=42)
        
        # Load data
        logger.info("\n📂 Loading processed crop features...")
        X = baseline.load_data('data/processed/crop_processed.csv')
        
        # Load yield target
        logger.info("\n🎯 Loading yield target...")
        y = baseline.load_raw_yield('data/processed/crop_raw_data.csv')
        
        # Prepare data
        logger.info("\n📊 Preparing train/test split...")
        X_train, X_test, y_train, y_test = baseline.prepare_data(X, y, test_size=0.2)
        
        # Train models
        logger.info("\n🚂 Training models...")
        baseline.train_and_evaluate(X_train, X_test, y_train, y_test)
        
        # Print summary
        logger.info("\n📈 Generating summary...")
        results_df = baseline.print_summary()
        
        # Save models
        logger.info("\n💾 Saving models...")
        baseline.save_models()
        
        # Export results
        logger.info("\n📊 Exporting results...")
        baseline.export_results()
        
        # Update registry
        logger.info("\n📚 Updating model registry...")
        baseline.update_registry()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ CROP BASELINE MODELS COMPLETE!")
        logger.info("=" * 80)
        
        logger.info("\n📝 PHASE 2 COMPLETION SUMMARY:")
        logger.info("   ✅ Crop data loaded: 19,689 records")
        logger.info("   ✅ Features engineered: 37 features")
        logger.info("   ✅ Baseline models trained: 3 models")
        logger.info("   ✅ Results exported: CSV + registry")
        logger.info("   ✅ Ready for Phase 3: Quantum Module!")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        logger.error(f"\n✗ Pipeline failed: {e}")
        raise
