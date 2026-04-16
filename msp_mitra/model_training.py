"""
Annadata MSP Mitra — Multi-Model Training Pipeline
====================================================
Trains and evaluates multiple ML models for crop price prediction:
  1. Linear Regression (baseline)
  2. Random Forest Regressor (n_estimators=200)
  3. XGBoost Regressor (primary model)

Each model is evaluated with RMSE, MAE, R² and persisted to disk.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import logging
import joblib

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    logging.warning("xgboost not installed — XGBoost model will be skipped")

from data_preprocessing import get_preprocessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


class ModelTrainer:
    """
    Trains Linear Regression, Random Forest, and XGBoost on
    preprocessed mandi price features. Evaluates with time-series
    aware train/test split.
    """

    def __init__(self):
        self.trained_models: Dict[str, Dict[str, Any]] = {}
        self.preprocessor = get_preprocessor()

    @staticmethod
    def _model_key(commodity: str, state: str, variety: Optional[str] = None) -> str:
        base = f"{commodity.lower().replace(' ', '_')}_{state.lower().replace(' ', '_')}"
        if variety:
            base += f"_{variety.lower().replace(' ', '_')}"
        return base

    # ------------------------------------------------------------------
    # Train / Test Split (time-series aware)
    # ------------------------------------------------------------------
    @staticmethod
    def time_split(
        df: pd.DataFrame,
        feature_cols: list,
        target: str = "modal_price",
        test_ratio: float = 0.2,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Split preserving temporal order — no shuffling."""
        split_idx = int(len(df) * (1 - test_ratio))
        X_train = df.iloc[:split_idx][feature_cols].values
        X_test = df.iloc[split_idx:][feature_cols].values
        y_train = df.iloc[:split_idx][target].values
        y_test = df.iloc[split_idx:][target].values
        return X_train, X_test, y_train, y_test

    # ------------------------------------------------------------------
    # Evaluation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        return {
            "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 2),
            "mae": round(float(mean_absolute_error(y_true, y_pred)), 2),
            "r2": round(float(r2_score(y_true, y_pred)), 4),
        }

    # ------------------------------------------------------------------
    # Core Training
    # ------------------------------------------------------------------
    def train_all_models(
        self,
        commodity: str,
        state: str,
        market: Optional[str] = None,
        variety: Optional[str] = None,
        raw_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Train all 3 models and return comparison results.
        """
        key = self._model_key(commodity, state, variety)

        # 1. Preprocess
        df, feature_cols = self.preprocessor.prepare_ml_dataset(
            commodity, state, market, variety, raw_df
        )

        if df.empty or len(df) < 30:
            logger.warning(f"Insufficient data for {key}: {len(df)} rows")
            return {"error": f"Need ≥30 data points, got {len(df)}"}

        # 2. Split
        X_train, X_test, y_train, y_test = self.time_split(df, feature_cols)
        logger.info(
            f"Train/Test split: {len(X_train)}/{len(X_test)} for {key}"
        )

        results: Dict[str, Any] = {
            "models": {},
            "metrics": {},
            "feature_cols": feature_cols,
            "best_model": None,
            "training_info": {
                "commodity": commodity,
                "state": state,
                "market": market,
                "total_rows": len(df),
                "train_rows": len(X_train),
                "test_rows": len(X_test),
                "features_count": len(feature_cols),
                "trained_at": datetime.now().isoformat(),
            },
        }

        # ------- Linear Regression -------
        try:
            lr = LinearRegression()
            lr.fit(X_train, y_train)
            lr_pred = lr.predict(X_test)
            lr_metrics = self.evaluate(y_test, lr_pred)
            results["models"]["linear_regression"] = lr
            results["metrics"]["linear_regression"] = lr_metrics
            logger.info(f"  LR  → R²={lr_metrics['r2']}, RMSE={lr_metrics['rmse']}")
        except Exception as e:
            logger.error(f"Linear Regression failed: {e}")

        # ------- Random Forest -------
        try:
            rf = RandomForestRegressor(
                n_estimators=200,
                max_depth=15,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=1,
            )
            rf.fit(X_train, y_train)
            rf_pred = rf.predict(X_test)
            rf_metrics = self.evaluate(y_test, rf_pred)
            results["models"]["random_forest"] = rf
            results["metrics"]["random_forest"] = rf_metrics
            logger.info(f"  RF  → R²={rf_metrics['r2']}, RMSE={rf_metrics['rmse']}")
        except Exception as e:
            logger.error(f"Random Forest failed: {e}")

        # ------- XGBoost -------
        if XGB_AVAILABLE:
            try:
                xgb_model = xgb.XGBRegressor(
                    n_estimators=300,
                    max_depth=8,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=1.0,
                    random_state=42,
                    n_jobs=1,
                    verbosity=0,
                )
                xgb_model.fit(
                    X_train,
                    y_train,
                    eval_set=[(X_test, y_test)],
                    verbose=False,
                )
                xgb_pred = xgb_model.predict(X_test)
                xgb_metrics = self.evaluate(y_test, xgb_pred)
                results["models"]["xgboost"] = xgb_model
                results["metrics"]["xgboost"] = xgb_metrics
                logger.info(
                    f"  XGB → R²={xgb_metrics['r2']}, RMSE={xgb_metrics['rmse']}"
                )
            except Exception as e:
                logger.error(f"XGBoost failed: {e}")

        # ------- Best model -------
        if results["metrics"]:
            best = max(
                results["metrics"].items(), key=lambda x: x[1]["r2"]
            )
            results["best_model"] = best[0]
            logger.info(f"  BEST → {best[0]} (R²={best[1]['r2']})")

        # ------- Persist -------
        self._save_models(key, results)
        self.trained_models[key] = results

        return results

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _save_models(self, key: str, results: Dict[str, Any]):
        """Save trained models + metadata to disk."""
        save_path = MODEL_DIR / f"{key}_trained.joblib"
        # Save only serializable parts
        save_data = {
            "models": results["models"],
            "metrics": results["metrics"],
            "feature_cols": results["feature_cols"],
            "best_model": results["best_model"],
            "training_info": results["training_info"],
        }
        joblib.dump(save_data, save_path)
        logger.info(f"Models saved → {save_path}")

    def load_models(self, commodity: str, state: str, variety: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Load trained models from disk."""
        key = self._model_key(commodity, state, variety)

        # Check memory cache first
        if key in self.trained_models:
            return self.trained_models[key]

        # Try disk
        save_path = MODEL_DIR / f"{key}_trained.joblib"
        if save_path.exists():
            try:
                data = joblib.load(save_path)
                self.trained_models[key] = data
                logger.info(f"Loaded models from {save_path}")
                return data
            except Exception as e:
                logger.error(f"Failed to load models: {e}")

        return None

    def get_model_comparison(
        self, commodity: str, state: str, variety: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Return metrics comparison table for all trained models."""
        data = self.load_models(commodity, state, variety)
        if not data:
            return None

        return {
            "commodity": commodity,
            "state": state,
            "metrics": data["metrics"],
            "best_model": data["best_model"],
            "training_info": data["training_info"],
        }

    def get_feature_importance(
        self, commodity: str, state: str
    ) -> Optional[Dict[str, Any]]:
        """Return feature importance from tree-based models."""
        data = self.load_models(commodity, state)
        if not data:
            return None

        importance = {}
        feature_cols = data["feature_cols"]

        # Random Forest importance
        if "random_forest" in data["models"]:
            rf = data["models"]["random_forest"]
            imp = rf.feature_importances_
            importance["random_forest"] = {
                feature_cols[i]: round(float(imp[i]), 4)
                for i in np.argsort(imp)[::-1]
            }

        # XGBoost importance
        if "xgboost" in data["models"]:
            xgb_model = data["models"]["xgboost"]
            imp = xgb_model.feature_importances_
            importance["xgboost"] = {
                feature_cols[i]: round(float(imp[i]), 4)
                for i in np.argsort(imp)[::-1]
            }

        return importance


# --------------- Singleton ---------------
_trainer: Optional[ModelTrainer] = None


def get_trainer() -> ModelTrainer:
    global _trainer
    if _trainer is None:
        _trainer = ModelTrainer()
    return _trainer
