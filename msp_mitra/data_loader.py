"""
MSP Mitra - Data Loader Module
Handles loading and filtering of agricultural price data from CSV
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to data files
DATA_DIR = Path(__file__).resolve().parent
PRICE_CSV = DATA_DIR / "agmarknet_india_historical_prices_2024_2025.csv"
MANDI_CSV = DATA_DIR / "data" / "mandi_master.csv"


class PriceDataLoader:
    """Load and query agricultural price data"""
    
    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.commodities: List[str] = []
        self.states: List[str] = []
        self.markets: List[str] = []
        self._load_data()
    
    def _load_data(self):
        """Load the price CSV into memory"""
        try:
            if not PRICE_CSV.exists():
                logger.error(f"Price data not found at {PRICE_CSV}")
                return
            
            logger.info(f"Loading price data from {PRICE_CSV}...")
            self.df = pd.read_csv(PRICE_CSV)
            
            # Parse date column
            self.df['Price Date'] = pd.to_datetime(
                self.df['Price Date'], 
                format='%d %b %Y',
                errors='coerce'
            )
            
            # Clean data
            self.df = self.df.dropna(subset=['Price Date', 'Modal Price (Rs./Quintal)'])
            
            # Cache unique values for dropdowns
            self.commodities = sorted(self.df['Commodity'].dropna().unique().tolist())
            self.states = sorted(self.df['State'].dropna().unique().tolist())
            self.markets = sorted(self.df['Market Name'].dropna().unique().tolist())
            
            logger.info(f"✓ Loaded {len(self.df):,} price records")
            logger.info(f"  Commodities: {len(self.commodities)}")
            logger.info(f"  States: {len(self.states)}")
            logger.info(f"  Markets: {len(self.markets)}")
            
        except Exception as e:
            logger.error(f"Failed to load price data: {e}")
            self.df = pd.DataFrame()
    
    def get_prices(
        self,
        commodity: str,
        state: Optional[str] = None,
        market: Optional[str] = None,
        variety: Optional[str] = None,
        days: int = 90
    ) -> pd.DataFrame:
        """
        Get price data for a commodity, optionally filtered by state/market/variety
        """
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        # Filter by commodity
        mask = self.df['Commodity'].str.lower() == commodity.lower()
        
        # Filter by state if provided
        if state:
            mask &= self.df['State'].str.lower() == state.lower()
        
        # Filter by market if provided
        if market:
            mask &= self.df['Market Name'].str.lower() == market.lower()

        # Filter by variety if provided
        if variety:
            mask &= self.df['Variety'].str.lower() == variety.lower()
        
        # Filter by date range
        cutoff_date = datetime.now() - timedelta(days=days)
        mask &= self.df['Price Date'] >= cutoff_date
        
        result = self.df[mask].copy()
        result = result.sort_values('Price Date', ascending=True)
        
        return result

    def get_latest_prices(
        self,
        commodity: str,
        state: Optional[str] = None,
        variety: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get latest prices across markets for a commodity.
        Fails over to simulated data if no records found.
        """
        if self.df is not None and not self.df.empty:
            mask = self.df['Commodity'].str.lower() == commodity.lower()
            if state:
                mask &= self.df['State'].str.lower() == state.lower()
            if variety:
                mask &= self.df['Variety'].str.lower() == variety.lower()
            
            filtered = self.df[mask].copy()
            
            if not filtered.empty:
                # Get latest price per market
                latest = filtered.loc[
                    filtered.groupby('Market Name')['Price Date'].idxmax()
                ]
                # Sort by date descending
                latest = latest.sort_values('Price Date', ascending=False).head(limit)
                
                return [
                    {
                        'market': row['Market Name'],
                        'district': row['District Name'],
                        'state': row['State'],
                        'min_price': round(row['Min Price (Rs./Quintal)'], 2),
                        'max_price': round(row['Max Price (Rs./Quintal)'], 2),
                        'modal_price': round(row['Modal Price (Rs./Quintal)'], 2),
                        'date': row['Price Date'].strftime('%Y-%m-%d'),
                        'variety': row.get('Variety', 'N/A'),
                        'grade': row.get('Grade', 'N/A'),
                        'is_simulated': False
                    }
                    for _, row in latest.iterrows()
                ]

        # FALLBACK: Simulated Data for "Working Model" (User Request)
        logger.info(f"Generating simulated market data for {commodity} in {state}")
        baselines = {
            "Rice": 2300, "Paddy": 2100, "Wheat": 2275, "Cotton": 6800,
            "Soybean": 4600, "Mustard": 5450, "Potato": 1500, "Onion": 2000
        }
        base = baselines.get(commodity.capitalize(), 3000)
        
        # Generate few dummy markets for the state
        markets = ["Central Mandi", "District Market", "Farmers Hub", "APMC Yard", "Regional Plaza"]
        results = []
        for i, m in enumerate(markets[:limit]):
            noise = np.random.normal(1.0, 0.03)
            price = round(base * noise, 2)
            results.append({
                'market': f"{m} {i+1}",
                'district': "Main District",
                'state': state or "All India",
                'min_price': round(price * 0.95, 2),
                'max_price': round(price * 1.05, 2),
                'modal_price': price,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'variety': variety or "Common",
                'grade': "FAQ",
                'is_simulated': True
            })
        return results
    
    def get_price_for_prediction(
        self,
        commodity: str,
        state: str,
        market: Optional[str] = None,
        variety: Optional[str] = None
    ) -> pd.DataFrame:
        """Get aggregated daily prices for ML prediction"""
        prices = self.get_prices(commodity, state, market, variety, days=365)
        if prices.empty:
            return pd.DataFrame()
        daily = prices.groupby('Price Date').agg({'Modal Price (Rs./Quintal)': 'mean'}).reset_index()
        daily.columns = ['ds', 'y']
        return daily.sort_values('ds')
    
    def get_markets_by_state(self, state: str) -> List[str]:
        """Get all markets in a state"""
        if self.df is None or self.df.empty: return []
        mask = self.df['State'].str.lower() == state.lower()
        return sorted(self.df[mask]['Market Name'].dropna().unique().tolist())
    
    def get_price_volatility(self, commodity: str, state: str, days: int = 30) -> Dict[str, Any]:
        """Calculate price volatility (with simulated fallback)"""
        prices = self.get_prices(commodity, state, days=days)
        if prices.empty or len(prices) < 5:
            # Simulated Volatility for Demo
            return {
                'volatility_score': 4.5,
                'classification': 'MODERATE',
                'std_dev': 100.0,
                'mean_price': 2500.0,
                'coefficient_of_variation': 4.5,
                'is_simulated': True
            }
        modal_prices = prices['Modal Price (Rs./Quintal)']
        std_dev, mean_price = modal_prices.std(), modal_prices.mean()
        cv = (std_dev / mean_price * 100) if mean_price > 0 else 0
        return {
            'volatility_score': round(cv, 2),
            'classification': 'LOW' if cv < 5 else 'MODERATE' if cv < 10 else 'HIGH',
            'std_dev': round(std_dev, 2),
            'mean_price': round(mean_price, 2),
            'coefficient_of_variation': round(cv, 2),
            'is_simulated': False
        }
    
    def get_price_trends(self, commodity: str, state: str, days: int = 30) -> Dict[str, Any]:
        """Detect price trends (with simulated fallback)"""
        prices = self.get_prices(commodity, state, days=days)
        if prices.empty or len(prices) < 7:
            return {'trend': 'UPWARD', 'strength': 3.5, 'change_percent': 3.5, 'is_simulated': True}
        prices = prices.sort_values('Price Date')
        y = prices['Modal Price (Rs./Quintal)'].values
        x = np.arange(len(y))
        slope, _ = np.polyfit(x, y, 1)
        first, last = y[0], y[-1]
        change = ((last - first) / first * 100) if first > 0 else 0
        return {
            'trend': 'UPWARD' if change > 2 else 'DOWNWARD' if change < -2 else 'STABLE',
            'strength': round(abs(change), 2),
            'change_percent': round(change, 2),
            'is_simulated': False
        }
    
    def get_seasonal_patterns(self, commodity: str, state: Optional[str] = None) -> Dict[str, Any]:
        """Detect seasonal patterns (with simulated fallback)"""
        prices = self.get_prices(commodity, state, days=365)
        if prices.empty:
            return {
                'has_pattern': True, 
                'peak_month': 'October', 
                'peak_price': 2800, 
                'trough_month': 'April', 
                'trough_price': 2100, 
                'is_simulated': True,
                'monthly_averages': {
                    'Jan': 2400, 'Feb': 2300, 'Mar': 2200, 'Apr': 2100,
                    'May': 2250, 'Jun': 2400, 'Jul': 2600, 'Aug': 2700,
                    'Sep': 2750, 'Oct': 2800, 'Nov': 2700, 'Dec': 2550
                }
            }
        prices['month'] = prices['Price Date'].dt.month
        monthly_avg = prices.groupby('month')['Modal Price (Rs./Quintal)'].mean()
        peak_month, trough_month = monthly_avg.idxmax(), monthly_avg.idxmin()
        months = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'Jun', 7:'Jul', 8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'}
        return {
            'has_pattern': True,
            'peak_month': months.get(peak_month),
            'peak_price': round(monthly_avg[peak_month], 2),
            'trough_month': months.get(trough_month),
            'trough_price': round(monthly_avg[trough_month], 2),
            'is_simulated': False
        }

    def get_market_comparison(self, commodity: str, state: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """Compare prices per market (with simulated fallback)"""
        prices = self.get_latest_prices(commodity, state, limit=top_n)
        if not prices: return []
        avg_p = sum(p['modal_price'] for p in prices) / len(prices)
        for p in prices:
            p['diff_from_avg_percent'] = round((p['modal_price'] - avg_p) / avg_p * 100, 2)
            p['price_status'] = 'ABOVE_AVG' if p['diff_from_avg_percent'] > 0 else 'BELOW_AVG'
        return prices

# Singleton
_price_loader = None
def get_price_loader() -> PriceDataLoader:
    global _price_loader
    if _price_loader is None: _price_loader = PriceDataLoader()
    return _price_loader
