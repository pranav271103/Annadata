"""
MSP Mitra - Market Analytics Engine
Advanced market analysis and intelligence
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging

from data_loader import get_price_loader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MarketAnalytics:
    """Advanced market analysis engine"""
    
    def __init__(self):
        self.price_loader = get_price_loader()
    
    def calculate_volatility(
        self,
        commodity: str,
        state: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive volatility metrics
        """
        return self.price_loader.get_price_volatility(commodity, state, days)
    
    def detect_trends(
        self,
        commodity: str,
        state: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Comprehensive trend detection with strength indicators
        """
        trend_data = self.price_loader.get_price_trends(commodity, state, days)
        
        # Add visual indicators
        if trend_data['trend'] == 'UPWARD':
            trend_data['indicator'] = '↑'
            trend_data['color'] = 'green'
        elif trend_data['trend'] == 'DOWNWARD':
            trend_data['indicator'] = '↓'
            trend_data['color'] = 'red'
        else:
            trend_data['indicator'] = '→'
            trend_data['color'] = 'gray'
        
        # Add strength label
        strength = trend_data.get('strength', 0)
        if strength < 3:
            trend_data['strength_label'] = 'weak'
        elif strength < 7:
            trend_data['strength_label'] = 'moderate'
        elif strength < 15:
            trend_data['strength_label'] = 'strong'
        else:
            trend_data['strength_label'] = 'very strong'
        
        return trend_data
    
    def find_seasonal_patterns(
        self,
        commodity: str,
        state: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detect and analyze seasonal price patterns
        """
        patterns = self.price_loader.get_seasonal_patterns(commodity, state)
        
        if not patterns.get('has_pattern'):
            return patterns
        
        # Calculate seasonal strength (price variance across months)
        monthly_prices = list(patterns['monthly_averages'].values())
        avg_price = np.mean(monthly_prices)
        variance = np.std(monthly_prices)
        seasonal_strength = (variance / avg_price * 100) if avg_price > 0 else 0
        
        patterns['seasonal_strength'] = round(seasonal_strength, 2)
        patterns['seasonal_strength_label'] = (
            'weak' if seasonal_strength < 5 else
            'moderate' if seasonal_strength < 10 else
            'strong'
        )
        
        return patterns
    
    def detect_anomalies(
        self,
        commodity: str,
        state: str,
        days: int = 30,
        sensitivity: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Detect unusual price movements (spikes/drops)
        
        Args:
            sensitivity: Number of standard deviations for anomaly threshold
        """
        prices = self.price_loader.get_prices(commodity, state, days=days)
        
        if prices.empty or len(prices) < 10:
            return []
        
        prices = prices.sort_values('Price Date')
        modal_prices = prices['Modal Price (Rs./Quintal)']
        
        # Calculate z-scores
        mean = modal_prices.mean()
        std = modal_prices.std()
        
        if std == 0:
            return []
        
        anomalies = []
        
        for idx, row in prices.iterrows():
            price = row['Modal Price (Rs./Quintal)']
            z_score = (price - mean) / std
            
            if abs(z_score) > sensitivity:
                anomaly_type = 'SPIKE' if z_score > 0 else 'DROP'
                severity = 'HIGH' if abs(z_score) > 3 else 'MODERATE'
                
                anomalies.append({
                    'date': row['Price Date'].strftime('%Y-%m-%d'),
                    'market': row['Market Name'],
                    'price': round(price, 2),
                    'mean_price': round(mean, 2),
                    'deviation_percent': round(((price - mean) / mean * 100), 2),
                    'z_score': round(z_score, 2),
                    'type': anomaly_type,
                    'severity': severity
                })
        
        return sorted(anomalies, key=lambda x: abs(x['z_score']), reverse=True)
    
    def compare_markets(
        self,
        commodity: str,
        markets: List[str],
        state: str
    ) -> Dict[str, Any]:
        """
        Deep comparison across specified markets
        """
        comparison_data = []
        
        for market in markets:
            prices = self.price_loader.get_prices(commodity, state, market=market, days=30)
            
            if prices.empty:
                continue
            
            latest = prices.iloc[-1]
            modal_prices = prices['Modal Price (Rs./Quintal)']
            
            comparison_data.append({
                'market': market,
                'current_price': round(latest['Modal Price (Rs./Quintal)'], 2),
                'avg_price_30d': round(modal_prices.mean(), 2),
                'min_price_30d': round(modal_prices.min(), 2),
                'max_price_30d': round(modal_prices.max(), 2),
                'volatility': round(modal_prices.std(), 2),
                'last_updated': latest['Price Date'].strftime('%Y-%m-%d')
            })
        
        if not comparison_data:
            return {'markets': [], 'best_market': None, 'worst_market': None}
        
        # Sort by current price
        comparison_data = sorted(comparison_data, key=lambda x: x['current_price'], reverse=True)
        
        return {
            'markets': comparison_data,
            'best_market': comparison_data[-1]['market'] if comparison_data else None,
            'worst_market': comparison_data[0]['market'] if comparison_data else None,
            'price_spread': round(
                comparison_data[0]['current_price'] - comparison_data[-1]['current_price'], 2
            ) if len(comparison_data) > 1 else 0
        }
    
    def get_market_insights(
        self,
        commodity: str,
        state: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Generate comprehensive market intelligence report
        """
        # Gather all analytics
        volatility = self.calculate_volatility(commodity, state, days)
        trends = self.detect_trends(commodity, state, days)
        seasonal = self.find_seasonal_patterns(commodity, state)
        anomalies = self.detect_anomalies(commodity, state, days)
        market_comparison = self.price_loader.get_market_comparison(commodity, state)
        
        # Calculate overall market health score (0-100)
        health_score = 100
        
        # Penalize for high volatility
        if volatility['classification'] == 'VERY_HIGH':
            health_score -= 30
        elif volatility['classification'] == 'HIGH':
            health_score -= 20
        elif volatility['classification'] == 'MODERATE':
            health_score -= 10
        
        # Penalize for downward trend
        if trends['trend'] == 'DOWNWARD':
            health_score -= 15
        
        # Penalize for anomalies
        health_score -= min(len(anomalies) * 5, 20)
        
        health_score = max(0, min(100, health_score))
        
        # Health classification
        if health_score >= 80:
            health_status = 'EXCELLENT'
        elif health_score >= 60:
            health_status = 'GOOD'
        elif health_score >= 40:
            health_status = 'FAIR'
        else:
            health_status = 'POOR'
        
        return {
            'commodity': commodity,
            'state': state,
            'analysis_period_days': days,
            'market_health': {
                'score': round(health_score, 1),
                'status': health_status
            },
            'volatility': volatility,
            'trends': trends,
            'seasonal_patterns': seasonal,
            'anomalies': anomalies[:3],  # Top 3 anomalies
            'market_comparison': market_comparison[:5],  # Top 5 markets
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }


# Singleton instance
_analytics_engine: Optional[MarketAnalytics] = None


def get_analytics_engine() -> MarketAnalytics:
    """Get singleton MarketAnalytics instance"""
    global _analytics_engine
    if _analytics_engine is None:
        _analytics_engine = MarketAnalytics()
    return _analytics_engine
