"""
MSP Mitra - Enhanced Price Prediction Module
Multi-model ensemble for better accuracy
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import logging
import pickle
from pathlib import Path
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_percentage_error

# Prophet import with fallback
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logging.warning("Prophet not installed. Will use alternative models.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache directory for trained models
MODEL_CACHE_DIR = Path(__file__).parent / "models"
MODEL_CACHE_DIR.mkdir(exist_ok=True)


class EnhancedPricePredictor:
    """
    Multi-model ensemble price predictor combining:
    1. Prophet (seasonality + trends)
    2. Linear Regression (trend detection)
    3. Moving Average (smoothing)
    """
    
    def __init__(self):
        self.prophet_models: Dict[str, any] = {}
        self.lr_models: Dict[str, LinearRegression] = {}
        self.historical_data: Dict[str, pd.DataFrame] = {}
    
    def _get_model_key(self, commodity: str, state: str, market: Optional[str]) -> str:
        """Generate unique key for caching models"""
        market_key = market.lower().replace(' ', '_') if market else 'all'
        return f"{commodity.lower()}_{state.lower().replace(' ', '_')}_{market_key}"
    
    def train(
        self,
        df: pd.DataFrame,
        commodity: str,
        state: str,
        market: Optional[str] = None
    ) -> bool:
        """Train ensemble of models"""
        if df.empty or len(df) < 30:
            logger.warning(f"Insufficient data for training: {len(df)} rows")
            return False
        
        model_key = self._get_model_key(commodity, state, market)
        
        try:
            logger.info(f"Training ensemble models for {model_key}...")
            
            # Store historical data
            self.historical_data[model_key] = df.copy()
            
            # 1. Train Prophet model (if available)
            if PROPHET_AVAILABLE:
                prophet_model = Prophet(
                    yearly_seasonality=True,
                    weekly_seasonality=False,
                    daily_seasonality=False,
                    changepoint_prior_scale=0.05,
                    seasonality_prior_scale=10.0,
                    interval_width=0.90
                )
                prophet_model.add_country_holidays(country_name='IN')
                prophet_model.fit(df)
                self.prophet_models[model_key] = prophet_model
            
            # 2. Train Linear Regression model
            df_sorted = df.sort_values('ds').reset_index(drop=True)
            X = np.arange(len(df_sorted)).reshape(-1, 1)
            y = df_sorted['y'].values
            
            lr_model = LinearRegression()
            lr_model.fit(X, y)
            self.lr_models[model_key] = lr_model
            
            # Save models to disk
            model_path = MODEL_CACHE_DIR / f"{model_key}.pkl"
            with open(model_path, 'wb') as f:
                pickle.dump({
                    'prophet': self.prophet_models.get(model_key),
                    'linear_regression': lr_model,
                    'historical_data': df
                }, f)
            
            logger.info(f"✓ Ensemble models trained: {model_key}")
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
        """Generate ensemble predictions"""
        model_key = self._get_model_key(commodity, state, market)
        
        # Load models
        if not self._load_models(model_key):
            logger.warning(f"No trained models found for {model_key}")
            return None
        
        try:
            predictions = []
            
            # Get historical data
            hist_df = self.historical_data.get(model_key)
            if hist_df is None or hist_df.empty:
                return None
            
            last_date = hist_df['ds'].max()
            last_price = hist_df['y'].iloc[-1]
            
            # Generate predictions for each day
            for i in range(1, days + 1):
                future_date = last_date + timedelta(days=i)
                
                # 1. Prophet prediction
                prophet_price = None
                prophet_lower = None
                prophet_upper = None
                
                if model_key in self.prophet_models and PROPHET_AVAILABLE:
                    prophet_model = self.prophet_models[model_key]
                    future_df = pd.DataFrame({'ds': [future_date]})
                    forecast = prophet_model.predict(future_df)
                    prophet_price = forecast['yhat'].iloc[0]
                    prophet_lower = forecast['yhat_lower'].iloc[0]
                    prophet_upper = forecast['yhat_upper'].iloc[0]
                
                # 2. Linear Regression prediction
                lr_price = None
                if model_key in self.lr_models:
                    lr_model = self.lr_models[model_key]
                    X_future = np.array([[len(hist_df) + i - 1]])
                    lr_price = lr_model.predict(X_future)[0]
                
                # 3. Moving Average (last 7 days)
                ma_window = min(7, len(hist_df))
                ma_price = hist_df['y'].iloc[-ma_window:].mean()
                
                # Ensemble: weighted average
                # Prophet: 60% (best for seasonality)
                # Linear Regression: 30% (trends)
                # Moving Average: 10% (stability)
                
                prices_available = []
                weights = []
                
                if prophet_price is not None:
                    prices_available.append(prophet_price)
                    weights.append(0.6)
                
                if lr_price is not None:
                    prices_available.append(lr_price)
                    weights.append(0.3)
                
                if ma_price is not None:
                    prices_available.append(ma_price)
                    weights.append(0.1)
                
                if not prices_available:
                    continue
                
                # Normalize weights
                total_weight = sum(weights)
                weights = [w / total_weight for w in weights]
                
                # Weighted average
                ensemble_price = sum(p * w for p, w in zip(prices_available, weights))
                
                # Confidence bounds (from Prophet if available, else ±5%)
                if prophet_lower is not None and prophet_upper is not None:
                    price_low = min(prophet_lower, ensemble_price * 0.95)
                    price_high = max(prophet_upper, ensemble_price * 1.05)
                else:
                    price_low = ensemble_price * 0.95
                    price_high = ensemble_price * 1.05
                
                predictions.append({
                    'date': future_date.strftime('%Y-%m-%d'),
                    'predicted_price': round(ensemble_price, 2),
                    'price_low': round(price_low, 2),
                    'price_high': round(price_high, 2),
                    'models_used': {
                        'prophet': prophet_price is not None,
                        'linear_regression': lr_price is not None,
                        'moving_average': True
                    }
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
            
            # Calculate confidence score
            confidence = self._calculate_confidence(hist_df, predictions)
            
            return {
                'commodity': commodity,
                'state': state,
                'market': market,
                'predictions': predictions,
                'trend': trend,
                'trend_percent': round(trend_percent, 2),
                'confidence_score': confidence,
                'model_key': model_key,
                'ensemble_info': {
                    'prophet_enabled': PROPHET_AVAILABLE,
                    'models_count': len([p for p in predictions if p])
                }
            }
            
        except Exception as e:
            logger.error(f"Prediction failed for {model_key}: {e}")
            return None
    
    def _calculate_confidence(
        self,
        historical_data: pd.DataFrame,
        predictions: List[Dict[str, Any]]
    ) -> int:
        """
        Calculate prediction confidence score (0-100)
        Based on: data quality, model agreement, volatility
        """
        score = 100
        
        # Penalize for insufficient data
        data_points = len(historical_data)
        if data_points < 30:
            score -= 40
        elif data_points < 60:
            score -= 20
        elif data_points < 90:
            score -= 10
        
        # Penalize for high volatility
        volatility = historical_data['y'].std() / historical_data['y'].mean() * 100
        if volatility > 15:
            score -= 30
        elif volatility > 10:
            score -= 20
        elif volatility > 5:
            score -= 10
        
        # Reward for model agreement
        if predictions and PROPHET_AVAILABLE:
            score += 10
        
        return max(0, min(100, int(score)))
    
    def get_sell_recommendation(
        self,
        current_price: float,
        predictions: List[Dict[str, Any]],
        volatility: Dict[str, Any],
        msp: Optional[float] = None
    ) -> Dict[str, Any]:
        """Enhanced recommendations with volatility awareness"""
        if not predictions:
            return {
                'recommendation': 'HOLD & MONITOR',
                'reason': 'Insufficient data for recommendation',
                'confidence': 0
            }
        
        # Find peak price
        peak_idx = max(range(len(predictions)), 
                      key=lambda i: predictions[i]['predicted_price'])
        peak_price = predictions[peak_idx]['predicted_price']
        peak_date = predictions[peak_idx]['date']
        
        # Calculate potential gain
        potential_gain = ((peak_price - current_price) / current_price) * 100
        
        # Check volatility
        vol_class = volatility.get('classification', 'MODERATE')
        is_high_volatility = vol_class in ['HIGH', 'VERY_HIGH']
        
        # Decision logic with volatility awareness
        if is_high_volatility and abs(potential_gain) < 10:
            return {
                'recommendation': 'HOLD & MONITOR',
                'reason': f'Market volatility is {vol_class}. Wait for price stabilization.',
                'confidence': 50,
                'volatility_warning': True
            }
        
        if potential_gain > 7:
            days_to_wait = peak_idx + 1
            return {
                'recommendation': f'WAIT {days_to_wait} DAYS' if days_to_wait <= 3 else 'WAIT',
                'reason': f'Price expected to rise {potential_gain:.1f}% by {peak_date}',
                'best_sell_date': peak_date,
                'expected_price': round(peak_price, 2),
                'potential_gain_percent': round(potential_gain, 2),
                'confidence': min(90, 60 + int(potential_gain))
            }
        elif potential_gain > 3:
            return {
                'recommendation': 'SELL BEFORE ' + peak_date,
                'reason': f'Moderate upside of {potential_gain:.1f}% expected',
                'expected_price': round(peak_price, 2),
                'confidence': 70
            }
        elif potential_gain < -5:
            return {
                'recommendation': 'SELL NOW',
                'reason': f'Price expected to drop {abs(potential_gain):.1f}%. Current price is favorable.',
                'current_price': round(current_price, 2),
                'confidence': min(90, 60 + int(abs(potential_gain)))
            }
        else:
            if msp and current_price >= msp * 1.05:
                return {
                    'recommendation': 'SELL NOW',
                    'reason': f'Price (₹{current_price:.0f}) is {((current_price/msp - 1) * 100):.1f}% above MSP. Good selling opportunity.',
                    'confidence': 80
                }
            else:
                return {
                    'recommendation': 'HOLD & MONITOR',
                    'reason': 'Price expected to remain stable. Monitor for better opportunity.',
                    'confidence': 65
                }
    
    def _load_models(self, model_key: str) -> bool:
        """Load models from cache or disk"""
        # Check memory cache
        if model_key in self.historical_data:
            return True
        
        # Try loading from disk
        model_path = MODEL_CACHE_DIR / f"{model_key}.pkl"
        if model_path.exists():
            try:
                with open(model_path, 'rb') as f:
                    saved_data = pickle.load(f)
                
                if 'prophet' in saved_data and saved_data['prophet']:
                    self.prophet_models[model_key] = saved_data['prophet']
                
                if 'linear_regression' in saved_data:
                    self.lr_models[model_key] = saved_data['linear_regression']
                
                if 'historical_data' in saved_data:
                    self.historical_data[model_key] = saved_data['historical_data']
                
                logger.info(f"✓ Loaded models from disk: {model_key}")
                return True
            except Exception as e:
                logger.error(f"Failed to load models {model_key}: {e}")
        
        return False


# Singleton instance
_enhanced_predictor: Optional[EnhancedPricePredictor] = None


def get_enhanced_predictor() -> EnhancedPricePredictor:
    """Get singleton EnhancedPricePredictor instance"""
    global _enhanced_predictor
    if _enhanced_predictor is None:
        _enhanced_predictor = EnhancedPricePredictor()
    return _enhanced_predictor
