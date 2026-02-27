"""
MSP Mitra - Enhanced FastAPI Backend
Price Intelligence System with Advanced Analytics
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from data_loader import get_price_loader
from price_predictor_enhanced import get_enhanced_predictor
from market_analytics import get_analytics_engine
from insights_engine import get_insights_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="MSP Mitra - Price Intelligence API",
    description="Advanced Agricultural Price Analytics & Predictions for Indian Farmers",
    version="2.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services on startup
price_loader = None
predictor = None
analytics = None
insights = None


@app.on_event("startup")
async def startup_event():
    """Load data and initialize services"""
    global price_loader, predictor, analytics, insights
    logger.info("🚀 Starting MSP Mitra Price Intelligence API...")
    price_loader = get_price_loader()
    predictor = get_enhanced_predictor()
    analytics = get_analytics_engine()
    insights = get_insights_engine()
    logger.info("✓ MSP Mitra API ready!")


# ============================================================
# Pydantic Models
# ============================================================

class TrainRequest(BaseModel):
    commodity: str
    state: str
    market: Optional[str] = None


# ============================================================
# Core Endpoints
# ============================================================

@app.get("/")
async def root():
    """API info and status"""
    return {
        "service": "MSP Mitra - Price Intelligence System",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "Historical Price Data (1.1M+ records)",
            "Multi-Model Price Predictions",
            "Market Analytics & Insights",
            "Volatility Detection",
            "Trend Analysis",
            "Seasonal Pattern Recognition",
            "Smart Sell Recommendations"
        ],
        "endpoints": {
            "core": {
                "commodities": "/commodities",
                "states": "/states",
                "markets": "/markets/{state}",
                "prices": "/prices/{commodity}/{state}",
                "history": "/prices/history/{commodity}",
                "train": "/train (POST)",
                "predict": "/predict/{commodity}/{state}",
                "recommend": "/recommend/{commodity}/{state}"
            },
            "analytics": {
                "volatility": "/analytics/volatility/{commodity}/{state}",
                "trends": "/analytics/trends/{commodity}/{state}",
                "seasonal": "/analytics/seasonal/{commodity}",
                "market_comparison": "/analytics/market-comparison/{commodity}/{state}",
                "top_performers": "/analytics/top-performers/{state}",
                "insights": "/analytics/insights/{commodity}/{state}"
            }
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "data_loaded": price_loader is not None and price_loader.df is not None,
        "records_count": len(price_loader.df) if price_loader and price_loader.df is not None else 0,
        "services": {
            "price_loader": price_loader is not None,
            "predictor": predictor is not None,
            "analytics": analytics is not None,
            "insights": insights is not None
        }
    }


@app.get("/commodities")
async def get_commodities():
    """Get list of all available commodities"""
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    
    commodities = price_loader.get_commodities_list()
    
    return {
        "commodities": commodities,
        "count": len(commodities),
        "sample": commodities[:10] if len(commodities) > 10 else commodities
    }


@app.get("/states")
async def get_states():
    """Get list of all states"""
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    
    return {
        "states": price_loader.get_states_list(),
        "count": len(price_loader.states)
    }


@app.get("/markets/{state}")
async def get_markets(state: str):
    """Get all markets in a state"""
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    
    markets = price_loader.get_markets_by_state(state)
    
    if not markets:
        raise HTTPException(status_code=404, detail=f"No markets found for state: {state}")
    
    return {
        "state": state,
        "markets": markets,
        "count": len(markets)
    }


@app.get("/prices/{commodity}/{state}")
async def get_prices(
    commodity: str,
    state: str,
    limit: int = Query(20, ge=1, le=100)
):
    """Get latest prices for a commodity in a state"""
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    
    prices = price_loader.get_latest_prices(commodity, state, limit)
    
    if not prices:
        raise HTTPException(
            status_code=404, 
            detail=f"No prices found for {commodity} in {state}"
        )
    
    # Calculate stats
    all_prices = [p['modal_price'] for p in prices]
    avg_price = sum(all_prices) / len(all_prices)
    
    return {
        "commodity": commodity,
        "state": state,
        "prices": prices,
        "stats": {
            "average_price": round(avg_price, 2),
            "min_price": min(all_prices),
            "max_price": max(all_prices),
            "markets_count": len(prices)
        }
    }


@app.get("/prices/history/{commodity}")
async def get_price_history(
    commodity: str,
    state: Optional[str] = Query(None),
    days: int = Query(90, ge=7, le=365)
):
    """Get historical prices for charting"""
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    
    df = price_loader.get_price_for_prediction(commodity, state or "", None)
    
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No historical data found for {commodity}"
        )
    
    df = df.tail(days)
    
    history = [
        {
            "date": row['ds'].strftime('%Y-%m-%d'),
            "price": round(row['y'], 2)
        }
        for _, row in df.iterrows()
    ]
    
    return {
        "commodity": commodity,
        "state": state,
        "history": history,
        "days": len(history)
    }


@app.post("/train")
async def train_model(request: TrainRequest):
    """Train price prediction models"""
    if not price_loader or not predictor:
        raise HTTPException(status_code=503, detail="Services not loaded")
    
    df = price_loader.get_price_for_prediction(
        request.commodity, 
        request.state, 
        request.market
    )
    
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {request.commodity} in {request.state}"
        )
    
    if len(df) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient data. Need ≥30 records, got {len(df)}"
        )
    
    success = predictor.train(df, request.commodity, request.state, request.market)
    
    if not success:
        raise HTTPException(status_code=500, detail="Model training failed")
    
    return {
        "status": "success",
        "message": f"Ensemble models trained for {request.commodity} in {request.state}",
        "data_points": len(df),
        "market": request.market or "All markets"
    }


@app.get("/predict/{commodity}/{state}")
async def predict_prices(
    commodity: str,
    state: str,
    market: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=14)
):
    """Get price predictions using multi-model ensemble"""
    if not predictor:
        raise HTTPException(status_code=503, detail="Predictor not loaded")
    
    result = predictor.predict(commodity, state, market, days)
    
    if result is None:
        # Try auto-training
        df = price_loader.get_price_for_prediction(commodity, state, market)
        if not df.empty and len(df) >= 30:
            predictor.train(df, commodity, state, market)
            result = predictor.predict(commodity, state, market, days)
    
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No model for {commodity} in {state}. Train first via POST /train"
        )
    
    return result


@app.get("/recommend/{commodity}/{state}")
async def get_recommendation(
    commodity: str,
    state: str,
    current_price: float = Query(...),
    msp: Optional[float] = Query(None)
):
    """Get smart sell recommendation"""
    if not predictor or not price_loader:
        raise HTTPException(status_code=503, detail="Services not loaded")
    
    # Get predictions
    result = predictor.predict(commodity, state, None, days=7)
    
    if result is None:
        df = price_loader.get_price_for_prediction(commodity, state, None)
        if not df.empty and len(df) >= 30:
            predictor.train(df, commodity, state, None)
            result = predictor.predict(commodity, state, None, days=7)
    
    if result is None or not result.get('predictions'):
        raise HTTPException(
            status_code=404,
            detail=f"Cannot generate recommendation for {commodity} in {state}"
        )
    
    # Get volatility for better recommendation
    volatility = price_loader.get_price_volatility(commodity, state, days=30)
    
    # Generate recommendation
    recommendation = predictor.get_sell_recommendation(
        current_price,
        result['predictions'],
        volatility,
        msp
    )
    
    return {
        "commodity": commodity,
        "state": state,
        "current_price": current_price,
        "msp": msp,
        **recommendation,
        "forecast": result['predictions'][:5]
    }


# ============================================================
# Analytics Endpoints
# ============================================================

@app.get("/analytics/volatility/{commodity}/{state}")
async def get_volatility(
    commodity: str,
    state: str,
    days: int = Query(30, ge=7, le=90)
):
    """Get price volatility analysis"""
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not loaded")
    
    result = analytics.calculate_volatility(commodity, state, days)
    
    return {
        "commodity": commodity,
        "state": state,
        "days_analyzed": days,
        **result
    }


@app.get("/analytics/trends/{commodity}/{state}")
async def get_trends(
    commodity: str,
    state: str,
    days: int = Query(30, ge=7, le=90)
):
    """Get trend analysis"""
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not loaded")
    
    result = analytics.detect_trends(commodity, state, days)
    
    return {
        "commodity": commodity,
        "state": state,
        "days_analyzed": days,
        **result
    }


@app.get("/analytics/seasonal/{commodity}")
async def get_seasonal(
    commodity: str,
    state: Optional[str] = Query(None)
):
    """Get seasonal pattern analysis"""
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not loaded")
    
    result = analytics.find_seasonal_patterns(commodity, state)
    
    return {
        "commodity": commodity,
        "state": state,
        **result
    }


@app.get("/analytics/market-comparison/{commodity}/{state}")
async def get_market_comparison(
    commodity: str,
    state: str,
    top_n: int = Query(5, ge=3, le=10)
):
    """Compare prices across markets"""
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    
    result = price_loader.get_market_comparison(commodity, state, top_n)
    
    return {
        "commodity": commodity,
        "state": state,
        "markets": result,
        "count": len(result)
    }


@app.get("/analytics/top-performers/{state}")
async def get_top_performers(
    state: str,
    days: int = Query(30, ge=7, le=90),
    top_n: int = Query(5, ge=3, le=10)
):
    """Get best and worst performing commodities"""
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    
    result = price_loader.get_top_performers(state, days, top_n)
    
    return {
        "state": state,
        "days_analyzed": days,
        **result
    }


@app.get("/analytics/insights/{commodity}/{state}")
async def get_insights(
    commodity: str,
    state: str,
    days: int = Query(30, ge=7, le=90)
):
    """Get comprehensive AI-generated market insights"""
    if not analytics or not insights:
        raise HTTPException(status_code=503, detail="Services not loaded")
    
    # Generate comprehensive market analysis
    market_data = analytics.get_market_insights(commodity, state, days)
    
    # Generate natural language insights
    insight_texts = insights.generate_comprehensive_insights(
        commodity,
        state,
        market_data
    )
    
    return {
        "commodity": commodity,
        "state": state,
        "insights": insight_texts,
        "market_health": market_data.get('market_health'),
        "detailed_analytics": {
            "volatility": market_data.get('volatility'),
            "trends": market_data.get('trends'),
            "seasonal_patterns": market_data.get('seasonal_patterns'),
            "anomalies": market_data.get('anomalies', [])[:3],
            "top_markets": market_data.get('market_comparison', [])[:3]
        }
    }


# ============================================================
# Run Server
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
