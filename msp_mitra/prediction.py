"""
Annadata MSP Mitra — Prediction & Decision Engine
===================================================
Ensemble forecasting combining XGBoost (0.4), Random Forest (0.3),
Prophet (0.2), and Linear Regression (0.1).

Generates farmer-friendly sell/wait recommendations.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
import logging

from data_preprocessing import get_preprocessor
from model_training import get_trainer

# Prophet (optional)
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensemble weights
WEIGHTS = {
    "xgboost": 0.4,
    "random_forest": 0.3,
    "prophet": 0.2,
    "linear_regression": 0.1,
}


class PredictionEngine:
    """
    Forecasts future prices and generates actionable farmer advice.
    """

    def __init__(self):
        self.preprocessor = get_preprocessor()
        self.trainer = get_trainer()
        self._prophet_cache: Dict[str, Any] = {}

    @staticmethod
    def _key(commodity: str, state: str) -> str:
        return f"{commodity.lower().replace(' ', '_')}_{state.lower().replace(' ', '_')}"

    # ------------------------------------------------------------------
    # Prophet helper
    # ------------------------------------------------------------------
    def _get_prophet_predictions(
        self,
        commodity: str,
        state: str,
        days: int,
        variety: Optional[str] = None,
        raw_df: Optional[pd.DataFrame] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Train Prophet (if available) and forecast."""
        if not PROPHET_AVAILABLE:
            return None

        key = self._key(commodity, state)

        prophet_df = self.preprocessor.prepare_prophet_data(
            commodity, state, variety=variety, df=raw_df
        )
        if prophet_df.empty or len(prophet_df) < 30:
            return None

        try:
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10.0,
                interval_width=0.90,
            )
            model.add_country_holidays(country_name="IN")
            model.fit(prophet_df)
            self._prophet_cache[key] = model

            future = model.make_future_dataframe(periods=days)
            forecast = model.predict(future)
            tail = forecast.tail(days)

            return [
                {
                    "date": row["ds"].strftime("%Y-%m-%d"),
                    "price": round(float(row["yhat"]), 2),
                    "lower": round(float(row["yhat_lower"]), 2),
                    "upper": round(float(row["yhat_upper"]), 2),
                }
                for _, row in tail.iterrows()
            ]
        except Exception as e:
            logger.error(f"Prophet prediction failed: {e}")
            return None

    # ------------------------------------------------------------------
    # ML model predictions
    # ------------------------------------------------------------------
    def _get_ml_predictions(
        self,
        commodity: str,
        state: str,
        days: int,
        variety: Optional[str] = None,
        raw_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, List[float]]:
        """
        Generate future predictions from LR, RF, XGB
        """
        trained = self.trainer.load_models(commodity, state, variety)
        if not trained:
            return {}

        models = trained["models"]
        feature_cols = trained["feature_cols"]

        # Get the preprocessed historical data to seed lags
        df, _ = self.preprocessor.prepare_ml_dataset(
            commodity, state, variety=variety, df=raw_df
        )
        if df.empty:
            return {}

        # We'll use the last row's features and iteratively step forward
        last_row = df.iloc[-1].copy()
        last_date = df["Price Date"].iloc[-1]
        recent_prices = df["modal_price"].tail(30).tolist()

        results: Dict[str, List[float]] = {
            name: [] for name in models.keys()
        }

        for day_offset in range(1, days + 1):
            future_date = last_date + timedelta(days=day_offset)

            # Build feature vector
            features = {}
            features["day"] = future_date.day
            features["month"] = future_date.month
            features["year"] = future_date.year
            features["day_of_week"] = future_date.weekday()
            features["week_of_year"] = int(future_date.isocalendar()[1])
            features["quarter"] = (future_date.month - 1) // 3 + 1

            # Lag features from recent prices
            prices = recent_prices.copy()
            features["modal_price_lag_3"] = prices[-3] if len(prices) >= 3 else prices[-1]
            features["modal_price_lag_5"] = prices[-5] if len(prices) >= 5 else prices[-1]
            features["modal_price_lag_7"] = prices[-7] if len(prices) >= 7 else prices[-1]

            # Rolling features
            for w in [7, 14, 30]:
                window = prices[-w:] if len(prices) >= w else prices
                features[f"rolling_mean_{w}"] = np.mean(window)
            for w in [7, 14]:
                window = prices[-w:] if len(prices) >= w else prices
                features[f"rolling_std_{w}"] = np.std(window) if len(window) > 1 else 0

            # Momentum
            for p in [3, 7]:
                if len(prices) >= p + 1:
                    old = prices[-(p + 1)]
                    new = prices[-1]
                    features[f"pct_change_{p}"] = (new - old) / old if old > 0 else 0
                else:
                    features[f"pct_change_{p}"] = 0

            # Use last_row for remaining features
            features["min_price"] = last_row.get("min_price", prices[-1] * 0.95)
            features["max_price"] = last_row.get("max_price", prices[-1] * 1.05)
            features["price_spread"] = features["max_price"] - features["min_price"]
            features["num_markets"] = last_row.get("num_markets", 1)

            # Build feature array in correct order
            X = np.array(
                [[features.get(col, 0) for col in feature_cols]]
            )

            # Predict with each model
            for name, model in models.items():
                try:
                    pred = float(model.predict(X)[0])
                    pred = max(pred, 0)  # No negative prices
                    results[name].append(pred)
                except Exception:
                    results[name].append(recent_prices[-1])

            # Update recent_prices with ensemble prediction for next iteration
            day_preds = [results[name][-1] for name in results if results[name]]
            if day_preds:
                avg_pred = np.mean(day_preds)
                recent_prices.append(avg_pred)

        return results

    # ------------------------------------------------------------------
    # Ensemble Forecast
    # ------------------------------------------------------------------
    def predict(
        self,
        commodity: str,
        state: str,
        days: int = 7,
        variety: Optional[str] = None,
        raw_df: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate ensemble forecast for next N days.
        """
        # Get historical data
        temp_df, _ = self.preprocessor.prepare_ml_dataset(
            commodity, state, variety=variety, df=raw_df
        )

        if temp_df.empty:
            # Fallback to no variety
            if variety:
                temp_df, _ = self.preprocessor.prepare_ml_dataset(commodity, state, df=raw_df)
            
            if temp_df.empty:
                # USER REQUEST: Simulated fallback for missing data
                return self._get_simulated_forecast(commodity, state, days, variety)

        current_price = float(temp_df["modal_price"].iloc[-1])
        last_date = temp_df["Price Date"].iloc[-1]

        # Get predictions from ML models
        ml_preds = self._get_ml_predictions(commodity, state, days, variety, raw_df)
        
        # Rule-based fallback if ML fails (e.g. models not trained)
        if not ml_preds:
            logger.info("Using rule-based fallback for prediction")
            
            # Apply variety multipliers
            multiplier = 1.0
            v_lower = variety.lower() if variety else ""
            if "basmati" in v_lower: multiplier = 1.25
            elif "superior" in v_lower or "fine" in v_lower: multiplier = 1.15
            elif "common" in v_lower or "local" in v_lower: multiplier = 0.95
            
            base_p = current_price * multiplier
            ml_preds = {"rule_based": []}
            for i in range(1, days+1):
                # Simulated trend: Slight drift +/- 1%
                drift = 1.0 + (np.random.normal(0.002, 0.005) * i)
                ml_preds["rule_based"].append(base_p * drift)

        # Get Prophet predictions
        prophet_preds = self._get_prophet_predictions(
            commodity, state, days, variety, raw_df
        )

        # Build ensemble predictions
        predictions = []
        model_predictions: Dict[str, List[float]] = {}

        for i in range(days):
            future_date = last_date + timedelta(days=i + 1)
            weighted_sum = 0
            total_weight = 0
            models_used = {}
            day_prices = []

            for model_name, preds in ml_preds.items():
                if i < len(preds):
                    price = preds[i]
                    weight = WEIGHTS.get(model_name, 0.1)
                    weighted_sum += price * weight
                    total_weight += weight
                    models_used[model_name] = round(price, 2)
                    day_prices.append(price)

                    if model_name not in model_predictions:
                        model_predictions[model_name] = []
                    model_predictions[model_name].append(round(price, 2))

            if prophet_preds and i < len(prophet_preds):
                pp = prophet_preds[i]["price"]
                weight = WEIGHTS.get("prophet", 0.2)
                weighted_sum += pp * weight
                total_weight += weight
                models_used["prophet"] = round(pp, 2)
                day_prices.append(pp)

                if "prophet" not in model_predictions:
                    model_predictions["prophet"] = []
                model_predictions["prophet"].append(round(pp, 2))

            if total_weight > 0:
                ensemble_price = weighted_sum / total_weight
            else:
                continue

            # Confidence bounds
            if len(day_prices) >= 2:
                std = np.std(day_prices)
                price_low = ensemble_price - 1.5 * std
                price_high = ensemble_price + 1.5 * std
            else:
                price_low = ensemble_price * 0.95
                price_high = ensemble_price * 1.05

            pct_change = ((ensemble_price - current_price) / current_price * 100)

            predictions.append({
                "date": future_date.strftime("%Y-%m-%d"),
                "predicted_price": round(ensemble_price, 2),
                "price_low": round(max(price_low, 0), 2),
                "price_high": round(price_high, 2),
                "pct_change": round(pct_change, 2),
                "models_used": models_used,
            })

        if not predictions:
            return None

        first_pred = predictions[0]["predicted_price"]
        last_pred = predictions[-1]["predicted_price"]
        trend_pct = ((last_pred - first_pred) / first_pred * 100) if first_pred > 0 else 0

        if trend_pct > 2: trend = "RISING"
        elif trend_pct < -2: trend = "FALLING"
        else: trend = "STABLE"

        confidence = self._calculate_confidence(ml_preds, prophet_preds, len(temp_df))

        return {
            "commodity": commodity,
            "state": state,
            "variety": variety,
            "current_price": round(current_price, 2),
            "predictions": predictions,
            "trend": trend,
            "trend_percent": round(trend_pct, 2),
            "confidence_score": confidence,
            "model_predictions": model_predictions,
            "forecast_days": days,
            "is_simulated": False
        }

    # ------------------------------------------------------------------
    # Simulated/Demo Fallback (User Request)
    # ------------------------------------------------------------------
    def _get_simulated_forecast(
        self,
        commodity: str,
        state: str,
        days: int,
        variety: Optional[str] = None
    ) -> Dict[str, Any]:
        """Provides a realistic simulated forecast when data is missing."""
        logger.info(f"Generating simulated forecast for {commodity} in {state}")
        
        # 1. Base Prices (Rs/Quintal)
        baselines = {
            "Rice": 2300, "Paddy": 2100, "Wheat": 2275, "Cotton": 6800,
            "Soybean": 4600, "Mustard": 5450, "Potato": 1500, "Onion": 2000,
            "Maize": 2090, "Gram": 5335, "Tur": 7000, "Moong": 8558
        }
        base_price = baselines.get(commodity.capitalize(), 3000)
        
        # 2. State Multipliers
        state_mults = {
            "Punjab": 1.05, "Haryana": 1.05, "Maharashtra": 1.0, 
            "Karnataka": 1.02, "Gujarat": 1.03, "Uttar Pradesh": 0.95,
            "West Bengal": 0.92, "Madhya Pradesh": 0.98
        }
        state_mult = state_mults.get(state, 1.0)
        
        # 3. Variety Multipliers
        var_mult = 1.0
        if variety:
            v_low = variety.lower()
            if "basmati" in v_low: var_mult = 1.3
            elif "superior" in v_low: var_mult = 1.15
            elif "common" in v_low: var_mult = 0.95
            
        current_price = base_price * state_mult * var_mult
        last_date = datetime.now() - timedelta(days=1)
        
        predictions = []
        model_predictions = {"simulated": []}
        
        for i in range(days):
            future_date = last_date + timedelta(days=i + 1)
            # Simulated trend: Slightly rising (0.4% per day)
            trend = 1.0 + (0.004 * (i + 1))
            noise = np.random.normal(1.0, 0.01)
            pred_p = current_price * trend * noise
            
            predictions.append({
                "date": future_date.strftime("%Y-%m-%d"),
                "predicted_price": round(pred_p, 2),
                "price_low": round(pred_p * 0.95, 2),
                "price_high": round(pred_p * 1.05, 2),
                "pct_change": round((pred_p - current_price) / current_price * 100, 2),
                "models_used": {"simulated_v3": round(pred_p, 2)}
            })
            model_predictions["simulated"].append(round(pred_p, 2))
            
        return {
            "commodity": commodity,
            "state": state,
            "variety": variety,
            "current_price": round(current_price, 2),
            "predictions": predictions,
            "trend": "RISING",
            "trend_percent": round((predictions[-1]["predicted_price"] - current_price) / current_price * 100, 2),
            "confidence_score": 75,
            "is_simulated": True,
            "model_predictions": model_predictions,
            "forecast_days": days,
        }

    def _calculate_confidence(
        self,
        ml_preds: Dict[str, List[float]],
        prophet_preds: Optional[List],
        data_points: int,
    ) -> int:
        """0-100 confidence based on model agreement and data quality."""
        score = 70
        if data_points >= 200: score += 15
        elif data_points >= 100: score += 10
        elif data_points >= 50: score += 5
        elif data_points < 30: score -= 20

        num_models = len(ml_preds)
        if prophet_preds: num_models += 1
        score += min(num_models * 3, 12)

        if ml_preds:
            first_day_preds = [preds[0] for preds in ml_preds.values() if preds]
            if prophet_preds:
                first_day_preds.append(prophet_preds[0]["price"])

            if len(first_day_preds) >= 2:
                cv = np.std(first_day_preds) / np.mean(first_day_preds) * 100
                if cv < 2: score += 10
                elif cv < 5: score += 5
                elif cv > 15: score -= 15

        return max(0, min(100, score))

    def get_recommendation(
        self,
        commodity: str,
        state: str,
        variety: Optional[str] = None,
        current_price: Optional[float] = None,
        msp: Optional[float] = None,
        raw_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """Generate farmer-friendly sell/wait recommendation."""
        forecast = self.predict(commodity, state, days=10, variety=variety, raw_df=raw_df)
        if not forecast:
            return {
                "action": "INSUFFICIENT_DATA",
                "reason": "Not enough data to generate recommendation.",
                "reason_hi": "सिफारिश के लिए पर्याप्त डेटा नहीं है।",
                "confidence": 0,
            }

        if current_price is None:
            current_price = forecast["current_price"]

        predictions = forecast["predictions"]
        if not predictions:
            return {"action": "ERROR", "reason": "Could not generate predictions.", "confidence": 0}

        peak_idx = max(range(len(predictions)), key=lambda i: predictions[i]["predicted_price"])
        peak_price = predictions[peak_idx]["predicted_price"]
        peak_date = predictions[peak_idx]["date"]
        days_to_peak = peak_idx + 1

        trough_idx = min(range(len(predictions)), key=lambda i: predictions[i]["predicted_price"])
        trough_price = predictions[trough_idx]["predicted_price"]

        gain_pct = ((peak_price - current_price) / current_price * 100)
        loss_pct = ((trough_price - current_price) / current_price * 100)

        confidence = forecast["confidence_score"]
        conf_label = "High" if confidence >= 75 else "Medium" if confidence >= 50 else "Low"

        if gain_pct > 7:
            action = f"WAIT_{days_to_peak}_DAYS"
            reason = f"Price expected to increase by {gain_pct:.1f}% to ₹{peak_price:.0f}/qt by {peak_date}."
            reason_hi = f"कीमत {gain_pct:.1f}% बढ़कर ₹{peak_price:.0f}/क्विंटल होने की उम्मीद है {peak_date} तक।"
        elif loss_pct < -5:
            action = "SELL_NOW"
            reason = f"Price expected to drop. Current price ₹{current_price:.0f}/qt is favorable. Sell now!"
            reason_hi = f"कीमत गिरने की उम्मीद है। वर्तमान ₹{current_price:.0f}/क्विंटल अनुकूल है। अभी बेचें!"
        else:
            action = "HOLD_MONITOR"
            reason = f"Price expected to remain stable (±{abs(gain_pct):.1f}%) . Monitor market."
            reason_hi = f"कीमत स्थिर रहने की उम्मीद (±{abs(gain_pct):.1f}%)। बाजार पर नज़र रखें।"

        return {
            "action": action,
            "reason": reason,
            "reason_hi": reason_hi,
            "confidence": confidence,
            "confidence_label": conf_label,
            "current_price": round(current_price, 2),
            "peak_price": round(peak_price, 2),
            "peak_date": peak_date,
            "days_to_peak": days_to_peak,
            "potential_gain_pct": round(gain_pct, 2),
            "potential_loss_pct": round(loss_pct, 2),
            "trend": forecast["trend"],
            "forecast_summary": predictions[:5],
            "is_simulated": forecast.get("is_simulated", False)
        }


# --------------- Singleton ---------------
_engine: Optional[PredictionEngine] = None


def get_prediction_engine() -> PredictionEngine:
    global _engine
    if _engine is None:
        _engine = PredictionEngine()
    return _engine
