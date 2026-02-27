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
DATA_DIR = Path(__file__).resolve().parent.parent
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
        days: int = 90
    ) -> pd.DataFrame:
        """
        Get price data for a commodity, optionally filtered by state/market
        
        Args:
            commodity: Commodity name (e.g., "Wheat", "Rice")
            state: Optional state filter
            market: Optional market filter
            days: Number of days of history to return (default 90)
        
        Returns:
            DataFrame with price data
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
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get latest prices across markets for a commodity
        
        Returns list of dicts with market, price, date
        """
        if self.df is None or self.df.empty:
            return []
        
        mask = self.df['Commodity'].str.lower() == commodity.lower()
        
        if state:
            mask &= self.df['State'].str.lower() == state.lower()
        
        filtered = self.df[mask].copy()
        
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
                'min_price': row['Min Price (Rs./Quintal)'],
                'max_price': row['Max Price (Rs./Quintal)'],
                'modal_price': row['Modal Price (Rs./Quintal)'],
                'date': row['Price Date'].strftime('%Y-%m-%d'),
                'variety': row.get('Variety', 'N/A'),
                'grade': row.get('Grade', 'N/A')
            }
            for _, row in latest.iterrows()
        ]
    
    def get_price_for_prediction(
        self,
        commodity: str,
        state: str,
        market: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get aggregated daily prices for ML prediction
        Returns DataFrame with columns: ds (date), y (price)
        """
        prices = self.get_prices(commodity, state, market, days=365)
        
        if prices.empty:
            return pd.DataFrame()
        
        # Aggregate by date (average modal price across markets)
        daily = prices.groupby('Price Date').agg({
            'Modal Price (Rs./Quintal)': 'mean'
        }).reset_index()
        
        # Rename for Prophet
        daily.columns = ['ds', 'y']
        daily = daily.sort_values('ds')
        
        return daily
    
    def get_markets_by_state(self, state: str) -> List[str]:
        """Get all markets in a state"""
        if self.df is None or self.df.empty:
            return []
        
        mask = self.df['State'].str.lower() == state.lower()
        return sorted(self.df[mask]['Market Name'].dropna().unique().tolist())
    
    def get_commodities_list(self) -> List[str]:
        """Get list of all commodities"""
        return self.commodities
    
    def get_states_list(self) -> List[str]:
        """Get list of all states"""
        return self.states
    
    # ========== ADVANCED ANALYTICS METHODS ==========
    
    def get_price_volatility(
        self,
        commodity: str,
        state: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate price volatility for a commodity in a state
        Returns volatility score and classification
        """
        prices = self.get_prices(commodity, state, days=days)
        
        if prices.empty or len(prices) < 5:
            return {
                'volatility_score': 0,
                'classification': 'INSUFFICIENT_DATA',
                'std_dev': 0,
                'mean_price': 0,
                'coefficient_of_variation': 0
            }
        
        modal_prices = prices['Modal Price (Rs./Quintal)']
        
        std_dev = modal_prices.std()
        mean_price = modal_prices.mean()
        cv = (std_dev / mean_price * 100) if mean_price > 0 else 0
        
        # Classify volatility
        if cv < 5:
            classification = 'LOW'
        elif cv < 10:
            classification = 'MODERATE'
        elif cv < 15:
            classification = 'HIGH'
        else:
            classification = 'VERY_HIGH'
        
        return {
            'volatility_score': round(cv, 2),
            'classification': classification,
            'std_dev': round(std_dev, 2),
            'mean_price': round(mean_price, 2),
            'coefficient_of_variation': round(cv, 2),
            'data_points': len(prices)
        }
    
    def get_price_trends(
        self,
        commodity: str,
        state: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Detect price trends (upward, downward, stable)
        """
        prices = self.get_prices(commodity, state, days=days)
        
        if prices.empty or len(prices) < 7:
            return {
                'trend': 'INSUFFICIENT_DATA',
                'strength': 0,
                'change_percent': 0
            }
        
        # Calculate trend using linear regression
        prices = prices.sort_values('Price Date')
        y = prices['Modal Price (Rs./Quintal)'].values
        x = np.arange(len(y))
        
        # Fit line
        slope, intercept = np.polyfit(x, y, 1)
        
        # Calculate percent change
        first_price = y[0]
        last_price = y[-1]
        change_percent = ((last_price - first_price) / first_price * 100) if first_price > 0 else 0
        
        # Determine trend
        if abs(change_percent) < 2:
            trend = 'STABLE'
            strength = abs(change_percent)
        elif change_percent > 0:
            trend = 'UPWARD'
            strength = change_percent
        else:
            trend = 'DOWNWARD'
            strength = abs(change_percent)
        
        return {
            'trend': trend,
            'strength': round(strength, 2),
            'change_percent': round(change_percent, 2),
            'slope': round(slope, 2),
            'first_price': round(first_price, 2),
            'last_price': round(last_price, 2)
        }
    
    def get_seasonal_patterns(
        self,
        commodity: str,
        state: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detect seasonal price patterns across months
        """
        prices = self.get_prices(commodity, state, days=365)
        
        if prices.empty:
            return {'has_pattern': False, 'monthly_avg': {}}
        
        # Add month column
        prices['month'] = prices['Price Date'].dt.month
        
        # Calculate average price per month
        monthly_avg = prices.groupby('month')['Modal Price (Rs./Quintal)'].mean()
        
        # Find peak and trough months
        peak_month = monthly_avg.idxmax()
        trough_month = monthly_avg.idxmin()
        
        month_names = {
            1: 'January', 2: 'February', 3: 'March', 4: 'April',
            5: 'May', 6: 'June', 7: 'July', 8: 'August',
            9: 'September', 10: 'October', 11: 'November', 12: 'December'
        }
        
        return {
            'has_pattern': True,
            'peak_month': month_names.get(peak_month, 'Unknown'),
            'peak_price': round(monthly_avg[peak_month], 2),
            'trough_month': month_names.get(trough_month, 'Unknown'),
            'trough_price': round(monthly_avg[trough_month], 2),
            'monthly_averages': {
                month_names[m]: round(p, 2) 
                for m, p in monthly_avg.items()
            }
        }
    
    def get_market_comparison(
        self,
        commodity: str,
        state: str,
        top_n: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Compare prices across different markets for a commodity
        """
        prices = self.get_prices(commodity, state, days=30)
        
        if prices.empty:
            return []
        
        # Get latest price per market
        latest = prices.loc[
            prices.groupby('Market Name')['Price Date'].idxmax()
        ]
        
        # Sort by modal price descending
        latest = latest.sort_values('Modal Price (Rs./Quintal)', ascending=False)
        
        # Get average price for comparison
        avg_price = latest['Modal Price (Rs./Quintal)'].mean()
        
        results = []
        for _, row in latest.head(top_n).iterrows():
            modal_price = row['Modal Price (Rs./Quintal)']
            diff_from_avg = ((modal_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
            
            results.append({
                'market': row['Market Name'],
                'district': row['District Name'],
                'modal_price': round(modal_price, 2),
                'min_price': round(row['Min Price (Rs./Quintal)'], 2),
                'max_price': round(row['Max Price (Rs./Quintal)'], 2),
                'date': row['Price Date'].strftime('%Y-%m-%d'),
                'diff_from_avg_percent': round(diff_from_avg, 2),
                'price_status': 'ABOVE_AVG' if diff_from_avg > 0 else 'BELOW_AVG' if diff_from_avg < 0 else 'AVERAGE'
            })
        
        return results
    
    def get_top_performers(
        self,
        state: str,
        days: int = 30,
        top_n: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get best and worst performing commodities by price change
        """
        if self.df is None or self.df.empty:
            return {'gainers': [], 'losers': []}
        
        cutoff_date = datetime.now() - timedelta(days=days)
        state_mask = self.df['State'].str.lower() == state.lower()
        date_mask = self.df['Price Date'] >= cutoff_date
        
        filtered = self.df[state_mask & date_mask].copy()
        
        if filtered.empty:
            return {'gainers': [], 'losers': []}
        
        # Calculate price change per commodity
        performance = []
        
        for commodity in filtered['Commodity'].unique():
            comm_data = filtered[filtered['Commodity'] == commodity]
            comm_data = comm_data.sort_values('Price Date')
            
            if len(comm_data) < 2:
                continue
            
            first_price = comm_data.iloc[0]['Modal Price (Rs./Quintal)']
            last_price = comm_data.iloc[-1]['Modal Price (Rs./Quintal)']
            
            if first_price > 0:
                change_percent = ((last_price - first_price) / first_price * 100)
                
                performance.append({
                    'commodity': commodity,
                    'first_price': round(first_price, 2),
                    'last_price': round(last_price, 2),
                    'change_percent': round(change_percent, 2),
                    'change_amount': round(last_price - first_price, 2)
                })
        
        # Sort by change percent
        performance_df = pd.DataFrame(performance)
        
        if performance_df.empty:
            return {'gainers': [], 'losers': []}
        
        gainers = performance_df.nlargest(top_n, 'change_percent').to_dict('records')
        losers = performance_df.nsmallest(top_n, 'change_percent').to_dict('records')
        
        return {
            'gainers': gainers,
            'losers': losers
        }

# Singleton instance
_price_loader: Optional[PriceDataLoader] = None


def get_price_loader() -> PriceDataLoader:
    """Get singleton PriceDataLoader instance"""
    global _price_loader
    if _price_loader is None:
        _price_loader = PriceDataLoader()
    return _price_loader

