"""
MSP Mitra - Insights Engine
AI-powered natural language market insights
"""

from typing import Dict, List, Any
from datetime import datetime
import random

from data_loader import get_price_loader


class InsightsEngine:
    """Generate human-readable market insights"""
    
    def __init__(self):
        self.price_loader = get_price_loader()
    
    def generate_price_insight(
        self,
        commodity: str,
        state: str,
        current_price: float,
        mean_price: float,
        trend: str
    ) -> str:
        """Generate insight about current price vs average"""
        diff_percent = ((current_price - mean_price) / mean_price * 100) if mean_price > 0 else 0
        
        if abs(diff_percent) < 3:
            return f"{commodity} prices in {state} are stable around ₹{current_price:.0f}/quintal"
        elif diff_percent > 0:
            return f"{commodity} prices in {state} are {diff_percent:.1f}% higher than the 30-day average (₹{mean_price:.0f}/quintal)"
        else:
            return f"{commodity} prices in {state} are {abs(diff_percent):.1f}% lower than the 30-day average (₹{mean_price:.0f}/quintal)"
    
    def generate_trend_insight(
        self,
        trend_data: Dict[str, Any]
    ) -> str:
        """Generate insight about price trends"""
        trend = trend_data.get('trend', 'UNKNOWN')
        strength = trend_data.get('strength', 0)
        change_percent = trend_data.get('change_percent', 0)
        
        if trend == 'INSUFFICIENT_DATA':
            return "Not enough data to determine price trend"
        
        if trend == 'STABLE':
            return f"Prices are stable with minimal fluctuation ({abs(change_percent):.1f}% change)"
        elif trend == 'UPWARD':
            strength_word = 'Strong' if strength > 10 else 'Moderate' if strength > 5 else 'Slight'
            return f"{strength_word} upward trend detected - prices rose {change_percent:.1f}% in last 30 days"
        else:  # DOWNWARD
            strength_word = 'Sharp' if strength > 10 else 'Moderate' if strength > 5 else 'Slight'
            return f"{strength_word} downward trend detected - prices fell {abs(change_percent):.1f}% in last 30 days"
    
    def generate_volatility_insight(
        self,
        volatility_data: Dict[str, Any]
    ) -> str:
        """Generate insight about price volatility"""
        classification = volatility_data.get('classification', 'UNKNOWN')
        cv = volatility_data.get('coefficient_of_variation', 0)
        
        insights = {
            'LOW': f"Market volatility is LOW ({cv:.1f}%) - prices are stable and predictable",
            'MODERATE': f"Market volatility is MODERATE ({cv:.1f}%) - expect some price fluctuations",
            'HIGH': f"Market volatility is HIGH ({cv:.1f}%) - prices are fluctuating significantly",
            'VERY_HIGH': f"Market volatility is VERY HIGH ({cv:.1f}%) - extreme price swings detected, high risk"
        }
        
        return insights.get(classification, "Unable to assess volatility")
    
    def generate_seasonal_insight(
        self,
        seasonal_data: Dict[str, Any]
    ) -> str:
        """Generate insight about seasonal patterns"""
        if not seasonal_data.get('has_pattern'):
            return "No clear seasonal pattern detected in historical data"
        
        peak_month = seasonal_data.get('peak_month', 'Unknown')
        trough_month = seasonal_data.get('trough_month', 'Unknown')
        peak_price = seasonal_data.get('peak_price', 0)
        trough_price = seasonal_data.get('trough_price', 0)
        
        diff_percent = ((peak_price - trough_price) / trough_price * 100) if trough_price > 0 else 0
        
        return (
            f"Seasonal pattern: Prices typically peak in {peak_month} (₹{peak_price:.0f}) "
            f"and are lowest in {trough_month} (₹{trough_price:.0f}), "
            f"a variation of {diff_percent:.1f}%"
        )
    
    def generate_recommendation_insight(
        self,
        recommendation: str,
        confidence: int,
        expected_price: float = None,
        potential_gain_percent: float = None
    ) -> str:
        """Generate insight for sell recommendations"""
        insights = {
            'SELL NOW': f"Recommendation: SELL NOW ({confidence}% confidence). Prices are at attractive levels.",
            'WAIT': f"Recommendation: WAIT ({confidence}% confidence). Prices expected to rise further.",
            'HOLD': f"Recommendation: HOLD & MONITOR ({confidence}% confidence). Market is uncertain."
        }
        
        base_insight = insights.get(recommendation, "No clear recommendation available")
        
        if expected_price and potential_gain_percent:
            base_insight += f" Expected price: ₹{expected_price:.0f} (potential gain: {potential_gain_percent:.1f}%)"
        
        return base_insight
    
    def generate_market_comparison_insight(
        self,
        markets: List[Dict[str, Any]]
    ) -> str:
        """Generate insight about market price differences"""
        if not markets or len(markets) < 2:
            return "Insufficient data for market comparison"
        
        best = markets[-1]  # Lowest price (best for buying)
        worst = markets[0]  # Highest price
        
        price_diff = worst['modal_price'] - best['modal_price']
        diff_percent = (price_diff / best['modal_price'] * 100) if best['modal_price'] > 0 else 0
        
        return (
            f"Price varies by ₹{price_diff:.0f} ({diff_percent:.1f}%) across markets. "
            f"Best price in {best['market']} (₹{best['modal_price']:.0f}), "
            f"highest in {worst['market']} (₹{worst['modal_price']:.0f})"
        )
    
    def generate_comprehensive_insights(
        self,
        commodity: str,
        state: str,
        market_data: Dict[str, Any]
    ) -> List[str]:
        """
        Generate a comprehensive set of insights
        
        Args:
            market_data: Output from get_market_insights()
        
        Returns:
            List of insight strings
        """
        insights = []
        
        # Price level insight
        volatility = market_data.get('volatility', {})
        mean_price = volatility.get('mean_price', 0)
        
        # Get latest price
        latest_prices = self.price_loader.get_latest_prices(commodity, state, limit=1)
        current_price = latest_prices[0]['modal_price'] if latest_prices else mean_price
        
        trends = market_data.get('trends', {})
        
        insights.append(
            self.generate_price_insight(commodity, state, current_price, mean_price, trends.get('trend'))
        )
        
        # Trend insight
        insights.append(self.generate_trend_insight(trends))
        
        # Volatility insight
        insights.append(self.generate_volatility_insight(volatility))
        
        # Seasonal insight
        seasonal = market_data.get('seasonal_patterns', {})
        if seasonal.get('has_pattern'):
            insights.append(self.generate_seasonal_insight(seasonal))
        
        # Market comparison insight
        market_comparison = market_data.get('market_comparison', [])
        if market_comparison:
            insights.append(self.generate_market_comparison_insight(market_comparison))
        
        # Anomaly alerts
        anomalies = market_data.get('anomalies', [])
        if anomalies:
            anomaly = anomalies[0]
            insights.append(
                f"⚠️ Recent {anomaly['type'].lower()}: {anomaly['market']} reported "
                f"₹{anomaly['price']:.0f} ({anomaly['deviation_percent']:+.1f}% from average)"
            )
        
        # Market health
        health = market_data.get('market_health', {})
        health_status = health.get('status', 'UNKNOWN')
        health_score = health.get('score', 0)
        
        health_messages = {
            'EXCELLENT': f"✅ Market health is excellent ({health_score:.0f}/100) - optimal selling conditions",
            'GOOD': f"👍 Market health is good ({health_score:.0f}/100) - favorable conditions",
            'FAIR': f"⚠️ Market health is fair ({health_score:.0f}/100) - exercise caution",
            'POOR': f"❌ Market health is poor ({health_score:.0f}/100) - high risk, consider waiting"
        }
        
        insights.append(health_messages.get(health_status, ''))
        
        return [i for i in insights if i]  # Filter out empty strings


# Singleton instance
_insights_engine = None


def get_insights_engine() -> InsightsEngine:
    """Get singleton InsightsEngine instance"""
    global _insights_engine
    if _insights_engine is None:
        _insights_engine = InsightsEngine()
    return _insights_engine
