"""
QUANTUM VARIATIONAL REGRESSOR - OPTIMIZED VERSION
==================================================
Location: src/models/quantum/vqr_crop_yield.py

IMPROVEMENTS FROM PREVIOUS VERSION:
✓ Training data: 300 → 5,000 samples
✓ Iterations: 30 → 200 iterations  
✓ Circuit: 6 qubits → 4 qubits (simpler)
✓ Expected MSE: 10,032 → ~3,000-5,000

Date: November 15, 2025 - OPTIMIZED FOR BETTER PERFORMANCE
"""

import numpy as np
import pandas as pd
import logging
from pathlib import Path
from typing import Dict
import joblib
import time
import warnings

warnings.filterwarnings('ignore', category=DeprecationWarning)

from qiskit.circuit.library import ZZFeatureMap, RealAmplitudes
from qiskit.primitives import Estimator
from qiskit_machine_learning.algorithms import VQR
from qiskit_machine_learning.optimizers import COBYLA

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class QuantumCropYieldRegressor:
    """Optimized Quantum VQR with better hyperparameters"""
    
    def __init__(
        self,
        num_qubits: int = 4,              # ← REDUCED from 6
        feature_map_reps: int = 1,        # ← REDUCED from 2
        ansatz_reps: int = 1,             # ← REDUCED from 2
        max_iterations: int = 200,        # ← INCREASED from 30
        feature_compression: bool = True,
        target_features: int = 4          # ← REDUCED from 6 to match qubits
    ):
        """Initialize with optimized hyperparameters"""
        self.num_qubits = num_qubits
        self.feature_map_reps = feature_map_reps
        self.ansatz_reps = ansatz_reps
        self.max_iterations = max_iterations
        self.feature_compression = feature_compression
        self.target_features = target_features
        
        if self.num_qubits != self.target_features:
            self.num_qubits = self.target_features
        
        self.vqr = None
        self.pca = None
        self.feature_scaler = StandardScaler()
        self.y_scaler = StandardScaler()
        self.training_time = 0
        
        logger.info("="*80)
        logger.info("⚛️  QUANTUM VQR OPTIMIZED (Qiskit 1.4.5 + ML 0.8.4)")
        logger.info("="*80)
        logger.info(f"Configuration (OPTIMIZED):")
        logger.info(f"  Qubits: {self.num_qubits} (↓ reduced)")
        logger.info(f"  Feature Map Reps: {feature_map_reps} (↓ reduced)")
        logger.info(f"  Ansatz Reps: {ansatz_reps} (↓ reduced)")
        logger.info(f"  Max Iterations: {max_iterations} (↑ increased)")
        logger.info(f"  Total Parameters: {self.num_qubits + (self.num_qubits * self.ansatz_reps * 3)}")
        logger.info(f"  ✓ Qubits match features: {self.num_qubits} == {self.target_features}")
    
    def compress_features(self, X: np.ndarray, fit: bool = True) -> np.ndarray:
        """Compress features using PCA"""
        if not self.feature_compression:
            return X
        
        if fit:
            logger.info(f"  PCA: {X.shape[1]} → {self.target_features} features")
            self.pca = PCA(n_components=min(self.target_features, X.shape[1]))
            X_compressed = self.pca.fit_transform(X)
            explained_var = self.pca.explained_variance_ratio_.sum()
            logger.info(f"    Explained variance: {explained_var:.1%}")
            return X_compressed
        else:
            if self.pca is None:
                return X
            return self.pca.transform(X)
    
    def train(self, X_train: np.ndarray, y_train: np.ndarray):
        """Train optimized VQR"""
        logger.info("\n" + "="*80)
        logger.info("🚀 QUANTUM VQR TRAINING (OPTIMIZED)")
        logger.info("="*80)
        
        start_time = time.time()
        
        try:
            # Step 1: Preprocess
            logger.info("\n📊 Step 1: Preprocessing...")
            logger.info(f"  Input: {len(X_train)} samples × {X_train.shape[1]} features")
            
            X_scaled = self.feature_scaler.fit_transform(X_train)
            X_compressed = self.compress_features(X_scaled, fit=True)
            y_scaled = self.y_scaler.fit_transform(y_train.reshape(-1, 1)).flatten()
            
            logger.info(f"  Output: {len(X_compressed)} samples × {X_compressed.shape[1]} features")
            logger.info(f"  Target range: [{y_scaled.min():.2f}, {y_scaled.max():.2f}]")
            
            # Step 2: Build circuits
            logger.info("\n⚛️  Step 2: Building quantum circuits...")
            num_features = X_compressed.shape[1]
            
            feature_map = ZZFeatureMap(
                feature_dimension=num_features,
                reps=self.feature_map_reps,
                entanglement='linear'
            )
            logger.info(f"  Feature Map: {num_features} → {num_features} qubits, {feature_map.num_parameters} params")
            
            ansatz = RealAmplitudes(
                num_qubits=self.num_qubits,
                reps=self.ansatz_reps,
                entanglement='full'
            )
            logger.info(f"  Ansatz: {self.num_qubits} qubits, {ansatz.num_parameters} params")
            
            total_params = feature_map.num_parameters + ansatz.num_parameters
            logger.info(f"  Total parameters: {total_params}")
            logger.info(f"  Ratio: {len(X_compressed)} samples / {total_params} params = {len(X_compressed)/total_params:.1f}x")
            
            if feature_map.num_qubits != ansatz.num_qubits:
                raise ValueError(f"Qubit mismatch: {feature_map.num_qubits} vs {ansatz.num_qubits}")
            logger.info(f"  ✓ Qubits aligned: {feature_map.num_qubits} == {ansatz.num_qubits}")
            
            # Step 3: Create optimizer
            logger.info("\n🔧 Step 3: Configuring optimizer...")
            estimator = Estimator()
            optimizer = COBYLA(maxiter=self.max_iterations)
            logger.info(f"  Optimizer: COBYLA (maxiter={self.max_iterations})")
            
            # Step 4: Create VQR
            logger.info("\n🎯 Step 4: Creating VQR...")
            self.vqr = VQR(
                feature_map=feature_map,
                ansatz=ansatz,
                optimizer=optimizer,
                estimator=estimator,
                loss='squared_error',
                initial_point=None,
                callback=None
            )
            logger.info("  ✓ VQR created successfully")
            
            # Step 5: Train
            logger.info("\n🚂 Step 5: Training VQR...")
            logger.info(f"  Data: {len(X_compressed)} samples × {num_features} features")
            logger.info(f"  Iterations: {self.max_iterations} (this may take 5-15 minutes...)")
            
            self.vqr.fit(X_compressed, y_scaled)
            self.training_time = time.time() - start_time
            
            logger.info(f"  ✓ Training complete ({self.training_time:.2f}s = {self.training_time/60:.1f} min)")
            
            # Step 6: Evaluate
            logger.info("\n📈 Step 6: Training evaluation...")
            y_train_pred = self.vqr.predict(X_compressed)
            train_mse = mean_squared_error(y_scaled, y_train_pred)
            train_r2 = r2_score(y_scaled, y_train_pred)
            train_mae = mean_absolute_error(y_scaled, y_train_pred)
            
            logger.info(f"  Train MSE: {train_mse:.6f}")
            logger.info(f"  Train MAE: {train_mae:.6f}")
            logger.info(f"  Train R²:  {train_r2:.6f}")
            
            logger.info("\n" + "="*80)
            logger.info("✅ TRAINING SUCCESSFUL!")
            logger.info("="*80)
            
            return True
            
        except Exception as e:
            logger.error(f"\n✗ Training failed: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def predict(self, X_test: np.ndarray) -> np.ndarray:
        """Make predictions"""
        if self.vqr is None:
            raise ValueError("Model not trained")
        
        X_scaled = self.feature_scaler.transform(X_test)
        X_compressed = self.compress_features(X_scaled, fit=False)
        y_pred_scaled = self.vqr.predict(X_compressed)
        y_pred = self.y_scaler.inverse_transform(y_pred_scaled.reshape(-1, 1)).flatten()
        
        return y_pred
    
    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> Dict:
        """Evaluate on test set"""
        logger.info("\n" + "="*80)
        logger.info("📊 EVALUATION ON TEST SET")
        logger.info("="*80)
        
        y_pred = self.predict(X_test)
        
        mse = mean_squared_error(y_test, y_pred)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        rmse = np.sqrt(mse)
        
        logger.info(f"Test MSE:  {mse:.2f}")
        logger.info(f"Test RMSE: {rmse:.2f}")
        logger.info(f"Test MAE:  {mae:.2f}")
        logger.info(f"Test R²:   {r2:.4f}")
        
        return {
            'mse': mse,
            'rmse': rmse,
            'mae': mae,
            'r2': r2,
            'predictions': y_pred
        }
    
    def compare_baseline(self, quantum_mse: float, baseline_mse: float = 1302.62) -> None:
        """Compare to classical baseline"""
        logger.info("\n" + "="*80)
        logger.info("🎯 QUANTUM vs CLASSICAL BASELINE")
        logger.info("="*80)
        
        improvement = ((baseline_mse - quantum_mse) / baseline_mse) * 100
        
        logger.info(f"Random Forest Baseline: MSE = {baseline_mse:.2f}")
        logger.info(f"Quantum VQR:            MSE = {quantum_mse:.2f}")
        
        if quantum_mse < baseline_mse:
            logger.info(f"\n✅ QUANTUM ADVANTAGE: {improvement:.1f}% improvement!")
        else:
            logger.info(f"\n⚠️  Gap: {abs(improvement):.1f}% (classical ahead)")
        
        logger.info("="*80)
    
    def save_model(self, path: str = 'src/models/saved_models/quantum_vqr_optimized.pkl') -> None:
        """Save model"""
        if self.vqr is None:
            logger.warning("Model not trained")
            return
        
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self, path)
            logger.info(f"✓ Model saved: {path}")
        except Exception as e:
            logger.error(f"Error: {e}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    
    print("\n" + "="*80)
    print("⚛️  QUANTUM VARIATIONAL REGRESSION - OPTIMIZED")
    print("="*80)
    
    try:
        # Load
        logger.info("\n📂 Loading data...")
        X = pd.read_csv('data/processed/crop_processed.csv').values
        y = pd.read_csv('data/processed/crop_raw_data.csv')['Yield'].values
        logger.info(f"✓ Loaded: X {X.shape}, y {y.shape}")
        
        # Split
        logger.info("\n🔀 Splitting data...")
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Use LARGER subset
        logger.info("\n⚡ Using optimized training set...")
        train_size = 5000  # INCREASED from 300
        X_train_opt = X_train[:train_size]
        y_train_opt = y_train[:train_size]
        X_test_opt = X_test[:500]  # Larger test set
        y_test_opt = y_test[:500]
        
        logger.info(f"  Train: {len(X_train_opt)} samples (↑ from 300)")
        logger.info(f"  Test: {len(X_test_opt)} samples")
        
        # Create quantum regressor with OPTIMIZED parameters
        logger.info("\n🏗️  Creating optimized quantum regressor...")
        quantum_model = QuantumCropYieldRegressor(
            num_qubits=4,              # ← Simpler
            feature_map_reps=1,        # ← Fewer reps
            ansatz_reps=1,             # ← Fewer reps
            max_iterations=200,        # ← More iterations
            feature_compression=True,
            target_features=4          # ← Matches qubits
        )
        
        # Train
        logger.info("\n🚀 Training optimized model...")
        quantum_model.train(X_train_opt, y_train_opt)
        
        # Evaluate
        logger.info("\n📊 Evaluating...")
        metrics = quantum_model.evaluate(X_test_opt, y_test_opt)
        
        # Compare
        logger.info("\n📈 Comparing to baseline...")
        quantum_model.compare_baseline(
            quantum_mse=metrics['mse'],
            baseline_mse=1302.62
        )
        
        # Save
        logger.info("\n💾 Saving optimized model...")
        quantum_model.save_model()
        
        print("\n" + "="*80)
        print("✅ OPTIMIZED QUANTUM TRAINING COMPLETE!")
        print("="*80)
        print(f"\nFinal Results:")
        print(f"  Training samples: {len(X_train_opt)} (↑ from 300)")
        print(f"  Training time: {quantum_model.training_time:.1f}s")
        print(f"  Test MSE: {metrics['mse']:.2f} (vs RF: 1,302.62)")
        print(f"  Test R²:  {metrics['r2']:.4f}")
        print(f"  Test MAE: {metrics['mae']:.2f}")
        print("="*80 + "\n")
        
    except Exception as e:
        logger.error(f"\n✗ Failed: {e}")
        import traceback
        traceback.print_exc()
