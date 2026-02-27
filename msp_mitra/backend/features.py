"""
MSP Mitra - Additional Features API
Export, Alerts, and Enhanced Analytics
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import pandas as pd
from datetime import datetime
import io

from data_loader import get_price_loader
from market_analytics import get_analytics_engine

router = APIRouter(prefix="/features", tags=["features"])

price_loader = get_price_loader()
analytics = get_analytics_engine()


@router.get("/export/prices/{commodity}/{state}")
async def export_prices_csv(
    commodity: str,
    state: str,
    days: int = Query(90, ge=7, le=365)
):
    """
    Export price data as CSV
    """
    df = price_loader.get_prices(commodity, state, days=days)
    
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {commodity} in {state}"
        )
    
    # Convert to CSV
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_content = csv_buffer.getvalue()
    
    return {
        "filename": f"{commodity}_{state}_{datetime.now().strftime('%Y%m%d')}.csv",
        "content": csv_content,
        "rows": len(df)
    }


@router.get("/compare/commodities/{state}")
async def compare_commodities(
    state: str,
    commodities: str = Query(..., description="Comma-separated commodity names"),
    days: int = Query(30, ge=7, le=90)
):
    """
    Compare multiple commodities in a state
    """
    commodity_list = [c.strip() for c in commodities.split(',')]
    
    comparison_data = []
    
    for commodity in commodity_list:
        try:
            # Get latest price
            latest_prices = price_loader.get_latest_prices(commodity, state, limit=1)
            if not latest_prices:
                continue
            
            current_price = latest_prices[0]['modal_price']
            
            # Get analytics
            volatility = price_loader.get_price_volatility(commodity, state, days)
            trend = price_loader.get_price_trends(commodity, state, days)
            
            comparison_data.append({
                'commodity': commodity,
                'currentPrice': current_price,
                'volatility': volatility['volatility_score'],
                'volatilityClass': volatility['classification'],
                'trend': trend['trend'],
                'trendPercent': trend['change_percent'],
                'meanPrice': volatility['mean_price']
            })
        except Exception as e:
            print(f"Error processing {commodity}: {e}")
            continue
    
    return {
        'state': state,
        'commodities': comparison_data,
        'count': len(comparison_data)
    }


@router.get("/state-overview/{state}")
async def get_state_overview(
    state: str,
    days: int = Query(30, ge=7, le=90)
):
    """
    Get comprehensive state-level analytics
    """
    # Get top performers
    performers = price_loader.get_top_performers(state, days, top_n=5)
    
    # Get all commodities in state
    if not price_loader.df is None:
        state_mask = price_loader.df['State'].str.lower() == state.lower()
        state_commodities = price_loader.df[state_mask]['Commodity'].unique().tolist()
    else:
        state_commodities = []
    
    # Calculate average volatility across commodities
    volatility_scores = []
    for commodity in state_commodities[:10]:  # Sample top 10
        try:
            vol = price_loader.get_price_volatility(commodity, state, days)
            volatility_scores.append(vol['volatility_score'])
        except:
            continue
    
    avg_volatility = sum(volatility_scores) / len(volatility_scores) if volatility_scores else 0
    
    return {
        'state': state,
        'total_commodities': len(state_commodities),
        'average_volatility': round(avg_volatility, 2),
        'top_gainers': performers['gainers'],
        'top_losers': performers['losers'],
        'sample_commodities': state_commodities[:20]
    }


@router.get("/price-alerts/check/{commodity}/{state}")
async def check_price_alert(
    commodity: str,
    state: str,
    target_price: float = Query(..., description="Target price to alert on"),
    alert_type: str = Query("above", description="'above' or 'below'")
):
    """
    Check if current price meets alert condition
    """
    latest_prices = price_loader.get_latest_prices(commodity, state, limit=1)
    
    if not latest_prices:
        raise HTTPException(
            status_code=404,
            detail=f"No prices found for {commodity} in {state}"
        )
    
    current_price = latest_prices[0]['modal_price']
    
    alert_triggered = False
    if alert_type == "above" and current_price >= target_price:
        alert_triggered = True
    elif alert_type == "below" and current_price <= target_price:
        alert_triggered = True
    
    return {
        'commodity': commodity,
        'state': state,
        'current_price': current_price,
        'target_price': target_price,
        'alert_type': alert_type,
        'alert_triggered': alert_triggered,
        'price_difference': round(current_price - target_price, 2)
    }


@router.get("/recommendations/bulk/{state}")
async def get_bulk_recommendations(
    state: str,
    commodities: Optional[str] = Query(None, description="Comma-separated list, or all"),
    msp_prices: Optional[str] = Query(None, description="Comma-separated MSP values")
):
    """
    Get sell recommendations for multiple commodities at once
    """
    if commodities is None:
        # Get top 10 commodities
        if price_loader.df is not None:
            state_mask = price_loader.df['State'].str.lower() == state.lower()
            commodity_list = price_loader.df[state_mask]['Commodity'].unique().tolist()[:10]
        else:
            commodity_list = []
    else:
        commodity_list = [c.strip() for c in commodities.split(',')]
    
    # Parse MSP prices if provided
    msp_dict = {}
    if msp_prices:
        msp_values = [float(m.strip()) for m in msp_prices.split(',')]
        msp_dict = dict(zip(commodity_list, msp_values))
    
    recommendations = []
    
    for commodity in commodity_list:
        try:
            # Get latest price
            latest_prices = price_loader.get_latest_prices(commodity, state, limit=1)
            if not latest_prices:
                continue
            
            current_price = latest_prices[0]['modal_price']
            
            # Get volatility and trend
            volatility = price_loader.get_price_volatility(commodity, state, days=30)
            trend = price_loader.get_price_trends(commodity, state, days=30)
            
            # Simple recommendation logic
            if trend['trend'] == 'UPWARD' and trend['change_percent'] > 5:
                rec = 'WAIT'
            elif trend['trend'] == 'DOWNWARD' and trend['change_percent'] < -5:
                rec = 'SELL NOW'
            else:
                rec = 'HOLD'
            
            recommendations.append({
                'commodity': commodity,
                'current_price': current_price,
                'recommendation': rec,
                'trend': trend['trend'],
                'volatility': volatility['classification'],
                'confidence': 70  # Default confidence
            })
        except Exception as e:
            print(f"Error processing {commodity}: {e}")
            continue
    
    return {
        'state': state,
        'recommendations': recommendations,
        'count': len(recommendations)
    }
