"""
Annadata MSP Mitra — Unified Price Intelligence Service v3.0
============================================================
Combines 7 ML & Decision Engines:
1. Data Loader (1.1M records)
2. Data Preprocessing (Feature Engineering)
3. Model Training (LR, RF, XGBoost)
4. Prediction Engine (Ensemble Forecasting)
5. Location Engine (Nearest Mandis)
6. Crop Advisor (Harvest Windows)
7. Alert System (SQLAlchemy Integration)
"""

import os
import sys
import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# --- Path Bootstrapping ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MSP_MITRA_DIR = ROOT_DIR / "msp_mitra"
if str(MSP_MITRA_DIR) not in sys.path:
    sys.path.insert(0, str(MSP_MITRA_DIR))

# Shared Annadata OS Infrastructure
from services.shared.auth.router import router as auth_router, setup_rate_limiting
from services.shared.config import settings
from services.shared.db.session import init_db, close_db, get_db
from services.shared.db.models import PriceAlert

# Import v3.0 Engines (Deferred imports to prevent global locks)
# We handle imports inside the lifespan or as needed if stability is an issue.

logger = logging.getLogger("services.msp_mitra")

# Engine Singletons
price_loader = None
preprocessor = None
trainer = None
predictor = None
location_engine = None
crop_advisor = None
analytics_engine = None
insights_engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database and ML engines sequentially at startup."""
    global price_loader, preprocessor, trainer, predictor, location_engine, crop_advisor, analytics_engine, insights_engine
    
    logger.info("MSP Mitra v3.0: Starting initialization sequence...")
    
    # 1. Database
    try:
        await init_db()
        logger.info("  [1/8] Database connected.")
    except Exception as e:
        logger.error(f"  [1/8] DB Init Failed: {e}")

    # Sequential Engine Loading with Yields to prevent Windows Segfaults (Access Violation)
    try:
        from data_loader import get_price_loader
        price_loader = get_price_loader()
        logger.info("  [2/8] Price Loader ready (1.1M records).")
        await asyncio.sleep(0.1)
        
        from data_preprocessing import get_preprocessor
        preprocessor = get_preprocessor()
        logger.info("  [3/8] Preprocessor ready.")
        await asyncio.sleep(0.1)
        
        from model_training import get_trainer
        trainer = get_trainer()
        logger.info("  [4/8] Model Trainer ready.")
        await asyncio.sleep(0.1)
        
        from prediction import get_prediction_engine
        predictor = get_prediction_engine()
        logger.info("  [5/8] Prediction Engine ready.")
        await asyncio.sleep(0.1)
        
        from location_engine import get_location_engine
        location_engine = get_location_engine()
        logger.info("  [6/8] Location Engine ready.")
        await asyncio.sleep(0.1)
        
        from crop_advisor import get_crop_advisor
        crop_advisor = get_crop_advisor()
        logger.info("  [7/8] Crop Advisor ready.")
        await asyncio.sleep(0.1)
        
        from market_analytics import get_analytics_engine
        analytics_engine = get_analytics_engine()
        from insights_engine import get_insights_engine
        insights_engine = get_insights_engine()
        logger.info("  [8/8] Analytics & Insights Engines ready.")
        
        logger.info("MSP Mitra v3.0: All engines operational.")
    except Exception as e:
        logger.error(f"Engine Load Sequence Failed: {e}")
        
    yield
    
    logger.info("MSP Mitra v3.0: Shutting down...")
    await close_db()

app = FastAPI(
    title="Annadata MSP Mitra v3.0",
    description="Advanced Agricultural Price Intelligence & Decision Engine",
    version="3.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting
setup_rate_limiting(app)

# Include Shared Auth
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "msp_mitra", "version": "3.0.0"}

# --- Prediction Endpoints ---

@app.get("/predict")
async def predict_price(
    commodity: str,
    state: str,
    variety: Optional[str] = None,
    days: int = Query(7, ge=1, le=30)
):
    """Query-based route for predictions."""
    if predictor is None:
        raise HTTPException(status_code=503, detail="Prediction Engine not initialised")
    
    forecast = predictor.predict(commodity, state, days=days, variety=variety, raw_df=price_loader.df)
    if not forecast:
        # Check if the commodity/state exists at all in the dataset
        if price_loader.df[(price_loader.df['Commodity'] == commodity) & (price_loader.df['State'] == state)].empty:
            raise HTTPException(status_code=404, detail=f"No data found for {commodity} in {state}")
        raise HTTPException(status_code=404, detail="Insufficient data for prediction")
    
    return forecast

@app.get("/predict/{commodity}/{state}")
async def predict_price_path(
    commodity: str,
    state: str,
    days: int = Query(7, ge=1, le=30)
):
    """Legacy path-based route for predictions."""
    return await predict_price(commodity, state, days=days)

# --- Recommendation Endpoints ---

@app.get("/recommendation")
async def get_market_recommendation(
    commodity: str,
    state: str,
    variety: Optional[str] = None,
    msp: Optional[float] = None
):
    """Get AI-powered sell/wait recommendation."""
    if predictor is None:
        raise HTTPException(status_code=503, detail="Prediction Engine not initialised")
    
    rec = predictor.get_recommendation(commodity, state, variety=variety, msp=msp, raw_df=price_loader.df)
    return rec

# --- Price Browser Endpoints ---

@app.get("/latest-prices")
async def get_latest_market_prices(
    commodity: str,
    state: Optional[str] = None,
    variety: Optional[str] = None,
    limit: int = 10
):
    """Browse latest prices across different mandis."""
    if price_loader is None:
        raise HTTPException(status_code=503, detail="Data Loader not initialised")
    
    prices = price_loader.get_latest_prices(commodity, state, variety=variety, limit=limit)
    return {"commodity": commodity, "prices": prices}

@app.get("/prices/{commodity}/{state}")
async def get_latest_prices_path(
    commodity: str,
    state: str,
    limit: int = Query(10, ge=1, le=100)
):
    """Legacy path-based route for latest prices."""
    return await get_latest_market_prices(commodity, state, limit=limit)

# --- Analytics Endpoints ---

@app.get("/analytics/volatility/{commodity}/{state}")
async def get_volatility(
    commodity: str,
    state: str,
    days: int = Query(30, ge=7, le=90)
):
    """Calculate price volatility metrics."""
    if analytics_engine is None:
        raise HTTPException(status_code=503, detail="Analytics Engine not initialised")
    
    vol = analytics_engine.calculate_volatility(commodity, state, days)
    return vol

@app.get("/analytics/insights/{commodity}/{state}")
async def get_insights_endpoint(
    commodity: str,
    state: str,
    days: int = Query(30, ge=7, le=90)
):
    """Generate NLP insights using the Insights Engine."""
    if analytics_engine is None or insights_engine is None:
        raise HTTPException(status_code=530, detail="Analytics/Insights Engine not initialised")
        
    market_data = analytics_engine.get_market_insights(commodity, state, days)
    insights_list = insights_engine.generate_comprehensive_insights(commodity, state, market_data)
    return {"insights": insights_list}

# --- Mandi & Crop Advisory ---

@app.get("/mandi-recommendations")
async def get_mandi_recommendations(
    commodity: str,
    state: str,
    variety: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    district: Optional[str] = None
):
    """Find nearest mandis with best prices."""
    if location_engine is None or predictor is None:
        raise HTTPException(status_code=503, detail="Location/Prediction Engine not initialised")
        
    # 1. Get predictions for this commodity in this state
    forecast = predictor.predict(commodity, state, days=1, variety=variety, raw_df=price_loader.df)
    pred_price = forecast["predictions"][0]["predicted_price"] if forecast else 0
    
    # 2. Get nearest mandis
    recommendations = location_engine.find_nearest_mandis(
        lat=lat, lon=lon, district=district, 
        predicted_prices={commodity: pred_price}
    )
    
    return {
        "commodity": commodity,
        "state": state,
        "variety": variety,
        "recommendations": recommendations
    }

@app.get("/crop-advisory")
async def get_crop_advisory(
    crop: str,
    sowing_date: str,
    state: Optional[str] = None,
    variety: Optional[str] = None
):
    """Get harvest timing and predicted market outlook."""
    if crop_advisor is None:
        raise HTTPException(status_code=503, detail="Crop Advisor not initialised")
        
    # Try to get prediction for harvest window
    try:
        forecast = predictor.predict(crop, state or "All India", days=14, variety=variety, raw_df=price_loader.df)
        pred_price = forecast["predictions"][-1]["predicted_price"] if forecast else None
    except:
        pred_price = None
        
    advisory = crop_advisor.calculate_harvest_advisory(crop, sowing_date, pred_price)
    return advisory

# ---------------------------------------------------------------------------
# Alerts Endpoints
# ---------------------------------------------------------------------------

@app.post("/alerts")
async def create_price_alert(
    alert_in: dict,  # Flexible schema for now
    db: AsyncSession = Depends(get_db)
):
    """Create a persistent price alert in the database."""
    new_alert = PriceAlert(
        alert_id=str(uuid4())[:8],
        commodity=alert_in.get('commodity'),
        state=alert_in.get('state'),
        target_price=alert_in.get('target_price'),
        direction=alert_in.get('direction', 'above'),
        status="active"
    )
    db.add(new_alert)
    await db.commit()
    await db.refresh(new_alert)
    return {"status": "success", "alert": new_alert.to_dict()}

@app.get("/alerts")
async def list_alerts(db: AsyncSession = Depends(get_db)):
    """List all price alerts for the user."""
    result = await db.execute(select(PriceAlert))
    alerts = result.scalars().all()
    return [a.to_dict() for a in alerts]

# ---------------------------------------------------------------------------
# Training Trigger
# ---------------------------------------------------------------------------

@app.post("/train-models")
async def trigger_training(commodity: str, state: str, variety: Optional[str] = None):
    """Trigger ML model training for a specific commodity/state/variety."""
    if trainer is None:
        raise HTTPException(status_code=503, detail="Trainer not initialised")
        
    results = trainer.train_all_models(commodity, state, variety=variety, raw_df=price_loader.df)
    if "error" in results:
        raise HTTPException(status_code=400, detail=results["error"])
    return {"status": "success", "metrics": results["metrics"], "best_model": results["best_model"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
