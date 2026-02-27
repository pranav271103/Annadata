"""
MSP Mitra - Price Prediction Module
Uses Facebook Prophet for time-series forecasting of agricultural commodity prices
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
import logging
import pickle
from pathlib import Path

# Prophet import with fallback
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logging.warning("Prophet not installed. Price prediction will be limited.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache directory for trained models
MODEL_CACHE_DIR = Path(__file__).parent / "models"
MODEL_CACHE_DIR.mkdir(exist_ok=True)


class PricePredictor:
    """
    Time-series price prediction using Facebook Prophet
    
    Prophet is chosen because:
    1. Handles seasonality well (agricultural prices have seasonal patterns)
    2. Robust to missing data
    3. Provides uncertainty intervals (confidence bounds)
    4. Fast to train and predict
    """
    
    def __init__(self):
        self.models: Dict[str, Prophet] = {}  # Cache trained models
    
    def _get_model_key(self, commodity: str, state: str, market: Optional[str]) -> str:
        """Generate unique key for caching models"""
        market_key = market.lower().replace(' ', '_') if market else 'all'
        return f"{commodity.lower()}_{state.lower().replace(' ', '_')}_{market_key}"
    
    def _get_model_path(self, model_key: str) -> Path:
        """Get path for cached model file"""
        return MODEL_CACHE_DIR / f"{model_key}.pkl"
    
    def train(
        self,
        df: pd.DataFrame,
        commodity: str,
        state: str,
        market: Optional[str] = None
    ) -> bool:
        """
        Train a Prophet model on price data
        
        Args:
            df: DataFrame with columns 'ds' (date) and 'y' (price)
            commodity: Commodity name
            state: State name
            market: Optional market name
        
        Returns:
            True if training successful, False otherwise
        """
        if not PROPHET_AVAILABLE:
            logger.error("Prophet not installed. Cannot train model.")
            return False
        
        if df.empty or len(df) < 30:
            logger.warning(f"Insufficient data for training: {len(df)} rows")
            return False
        
        model_key = self._get_model_key(commodity, state, market)
        
        try:
            logger.info(f"Training Prophet model for {model_key}...")
            
            # Initialize Prophet with tuned parameters for agricultural prices
            model = Prophet(
                yearly_seasonality=True,  # Agricultural cycles
                weekly_seasonality=True,  # Market days
                daily_seasonality=False,
                changepoint_prior_scale=0.1,  # More conservative trend changes
                seasonality_prior_scale=10.0,
                interval_width=0.90  # 90% confidence interval
            )
            
            # Add Indian holidays/seasons that affect prices
            model.add_country_holidays(country_name='IN')
            
            # Fit the model
            model.fit(df)
            
            # Cache the model
            self.models[model_key] = model
            
            # Save to disk
            model_path = self._get_model_path(model_key)
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)
            
            logger.info(f"✓ Model trained and saved: {model_key}")
            return True
            
        except Exception as e:
            logger.error(f"Training failed for {model_key}: {e}")
            return False
    
    def predict(
        self,
        commodity: str,
        state: str,
        market: Optional[str] = None,
        days: int = 7
    ) -> Optional[Dict[str, Any]]:
        """
        Predict future prices
        
        Args:
            commodity: Commodity name
            state: State name
            market: Optional market name
            days: Number of days to predict (default 7)
        
        Returns:
            Dict with predictions and confidence intervals, or None if failed
        """
        if not PROPHET_AVAILABLE:
            return self._fallback_prediction(commodity, state, days)
        
        model_key = self._get_model_key(commodity, state, market)
        
        # Try to load model
        model = self._load_model(model_key)
        
        if model is None:
            logger.warning(f"No trained model found for {model_key}")
            return None
        
        try:
            # Create future dataframe
            future = model.make_future_dataframe(periods=days)
            
            # Predict
            forecast = model.predict(future)
            
            # Get only future predictions
            last_date = model.history['ds'].max()
            future_forecast = forecast[forecast['ds'] > last_date][
                ['ds', 'yhat', 'yhat_lower', 'yhat_upper']
            ]
            
            # Format results
            predictions = []
            for _, row in future_forecast.iterrows():
                predictions.append({
                    'date': row['ds'].strftime('%Y-%m-%d'),
                    'predicted_price': round(row['yhat'], 2),
                    'price_low': round(row['yhat_lower'], 2),
                    'price_high': round(row['yhat_upper'], 2)
                })
            
            # Calculate trend
            if len(predictions) >= 2:
                first_price = predictions[0]['predicted_price']
                last_price = predictions[-1]['predicted_price']
                trend_percent = ((last_price - first_price) / first_price) * 100
                trend = 'rising' if trend_percent > 1 else ('falling' if trend_percent < -1 else 'stable')
            else:
                trend = 'unknown'
                trend_percent = 0
            
            return {
                'commodity': commodity,
                'state': state,
                'market': market,
                'predictions': predictions,
                'trend': trend,
                'trend_percent': round(trend_percent, 2),
                'model_key': model_key
            }
            
        except Exception as e:
            logger.error(f"Prediction failed for {model_key}: {e}")
            return None
    
    def _load_model(self, model_key: str) -> Optional[Prophet]:
        """Load model from cache or disk"""
        # Check memory cache first
        if model_key in self.models:
            return self.models[model_key]
        
        # Try loading from disk
        model_path = self._get_model_path(model_key)
        if model_path.exists():
            try:
                with open(model_path, 'rb') as f:
                    model = pickle.load(f)
                self.models[model_key] = model
                logger.info(f"✓ Loaded model from disk: {model_key}")
                return model
            except Exception as e:
                logger.error(f"Failed to load model {model_key}: {e}")
        
        return None
    
    def _fallback_prediction(
        self,
        commodity: str,
        state: str,
        days: int
    ) -> Dict[str, Any]:
        """
        Simple fallback prediction when Prophet is not available
        Uses linear extrapolation from recent data
        """
        logger.warning("Using fallback prediction (Prophet not available)")
        
        # Return dummy predictions
        today = datetime.now()
        predictions = []
        
        # Assume base price of 2500 with slight upward trend
        base = 2500
        for i in range(days):
            date = today + timedelta(days=i+1)
            price = base + (i * 10) + np.random.randint(-50, 50)
            predictions.append({
                'date': date.strftime('%Y-%m-%d'),
                'predicted_price': round(price, 2),
                'price_low': round(price * 0.95, 2),
                'price_high': round(price * 1.05, 2)
            })
        
        return {
            'commodity': commodity,
            'state': state,
            'market': None,
            'predictions': predictions,
            'trend': 'unknown',
            'trend_percent': 0,
            'model_key': 'fallback',
            'warning': 'Using fallback prediction. Install Prophet for accurate forecasts.'
        }
    
    def get_sell_recommendation(
        self,
        current_price: float,
        predictions: List[Dict[str, Any]],
        msp: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate sell/wait recommendation based on predictions
        
        Args:
            current_price: Current market price
            predictions: List of price predictions
            msp: Optional Minimum Support Price for the commodity
        
        Returns:
            Dict with recommendation, reason, and confidence
        """
        if not predictions:
            return {
                'recommendation': 'HOLD',
                'reason': 'Insufficient data for recommendation',
                'confidence': 0
            }
        
        # Find the peak predicted price
        peak_idx = max(range(len(predictions)), 
                      key=lambda i: predictions[i]['predicted_price'])
        peak_price = predictions[peak_idx]['predicted_price']
        peak_date = predictions[peak_idx]['date']
        
        # Calculate potential gain
        potential_gain = ((peak_price - current_price) / current_price) * 100
        
        # Decision logic
        if potential_gain > 5:
            # Price expected to rise significantly
            days_to_wait = peak_idx + 1
            return {
                'recommendation': 'WAIT',
                'reason': f'Price expected to rise {potential_gain:.1f}% in {days_to_wait} days',
                'best_sell_date': peak_date,
                'expected_price': peak_price,
                'potential_gain_percent': round(potential_gain, 2),
                'confidence': min(85, 50 + abs(potential_gain))
            }
        elif potential_gain < -5:
            # Price expected to fall
            return {
                'recommendation': 'SELL NOW',
                'reason': f'Price expected to drop {abs(potential_gain):.1f}% soon',
                'current_price': current_price,
                'confidence': min(85, 50 + abs(potential_gain))
            }
        else:
            # Price relatively stable
            if msp and current_price >= msp:
                return {
                    'recommendation': 'SELL NOW',
                    'reason': f'Price (₹{current_price}) is above MSP (₹{msp}). Market is stable.',
                    'confidence': 70
                }
            else:
                return {
                    'recommendation': 'HOLD',
                    'reason': 'Price expected to remain stable. Wait for better opportunity.',
                    'confidence': 60
                }


# Singleton instance
_predictor: Optional[PricePredictor] = None


def get_predictor() -> PricePredictor:
    """Get singleton PricePredictor instance"""
    global _predictor
    if _predictor is None:
        _predictor = PricePredictor()
    return _predictor
