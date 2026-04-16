"""
Annadata MSP Mitra — FastAPI Backend (Enhanced v3.0)
=====================================================
Production-grade price intelligence API with:
  - Multi-model ML predictions (LR + RF + XGBoost + Prophet)
  - Location-based mandi recommendations (Haversine)
  - Crop advisory (yield + price combined)
  - Mock SMS/WhatsApp alerts (Hindi + English)
  - Full backward compatibility with existing endpoints

All original endpoints are preserved and working.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

# ---- Existing modules (backward compat) ----
from data_loader import get_price_loader
from market_analytics import get_analytics_engine
from insights_engine import get_insights_engine

# ---- New modules ----
from data_preprocessing import get_preprocessor
from model_training import get_trainer
from prediction import get_prediction_engine
from location_engine import get_location_engine
from crop_advisor import get_crop_advisor
from alerts import get_alert_system

# Prophet-based predictor (existing, kept for compat)
try:
    from price_predictor_enhanced import get_enhanced_predictor
except ImportError:
    get_enhanced_predictor = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# FastAPI App
# ============================================================
app = FastAPI(
    title="Annadata MSP Mitra — Price Intelligence API",
    description=(
        "Production-grade ML-powered agricultural price analytics, "
        "predictions, mandi recommendations, and farmer advisory. "
        "Powered by 1.1M+ AgMarkNet records."
    ),
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Service instances (initialized at startup) ----
price_loader = None
predictor_legacy = None
analytics = None
insights = None
preprocessor = None
trainer = None
prediction_engine = None
location_engine = None
crop_advisor = None
alert_system = None


@app.on_event("startup")
async def startup_event():
    global price_loader, predictor_legacy, analytics, insights
    global preprocessor, trainer, prediction_engine, location_engine
    global crop_advisor, alert_system

    logger.info("🚀 Starting Annadata MSP Mitra v3.0 ...")

    # Existing services
    price_loader = get_price_loader()
    if get_enhanced_predictor:
        predictor_legacy = get_enhanced_predictor()
    analytics = get_analytics_engine()
    insights = get_insights_engine()

    # New services
    preprocessor = get_preprocessor()
    trainer = get_trainer()
    prediction_engine = get_prediction_engine()
    location_engine = get_location_engine()
    crop_advisor = get_crop_advisor()
    alert_system = get_alert_system()

    logger.info("✅ All services initialized!")


# ============================================================
# Pydantic Request Models
# ============================================================
class TrainRequest(BaseModel):
    commodity: str
    state: str
    market: Optional[str] = None


class PredictRequest(BaseModel):
    commodity: str
    state: str
    days: int = Field(default=7, ge=1, le=15)
    market: Optional[str] = None


class NearestMandiRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    district: Optional[str] = None
    commodity: Optional[str] = None
    state: Optional[str] = None
    top_n: int = Field(default=10, ge=1, le=20)
    max_radius_km: float = Field(default=300, ge=10, le=1000)


class CropAdvisoryRequest(BaseModel):
    crop: str
    sowing_date: str  # YYYY-MM-DD
    state: Optional[str] = None
    predicted_price: Optional[float] = None


class AlertCreateRequest(BaseModel):
    commodity: str
    state: str
    target_price: float
    direction: str = Field(default="above", pattern="^(above|below)$")
    phone: str = ""
    language: str = Field(default="en", pattern="^(en|hi)$")
    market: Optional[str] = None


# ============================================================
# ROOT & HEALTH
# ============================================================
@app.get("/")
async def root():
    return {
        "service": "Annadata MSP Mitra — Price Intelligence System",
        "version": "3.0.0",
        "status": "running",
        "modules": [
            "Multi-Model ML (LR + RF + XGBoost + Prophet)",
            "Ensemble Price Prediction",
            "Location-Based Mandi Recommendations",
            "Crop Advisory (Yield + Price)",
            "SMS/WhatsApp Alerts (Mock)",
            "Market Analytics & Insights",
        ],
        "new_endpoints": {
            "predict_price": "POST /predict-price",
            "train_models": "POST /train-models",
            "model_comparison": "GET /model-comparison/{commodity}/{state}",
            "nearest_mandis": "POST /nearest-mandis",
            "recommendation": "GET /recommendation/{commodity}/{state}",
            "crop_advisory": "POST /crop-advisory",
            "crop_list": "GET /crops",
            "create_alert": "POST /alerts/create",
            "list_alerts": "GET /alerts",
            "all_mandis": "GET /mandis",
        },
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "data_loaded": price_loader is not None and price_loader.df is not None,
        "records_count": len(price_loader.df) if price_loader and price_loader.df is not None else 0,
        "services": {
            "price_loader": price_loader is not None,
            "preprocessor": preprocessor is not None,
            "trainer": trainer is not None,
            "prediction_engine": prediction_engine is not None,
            "location_engine": location_engine is not None,
            "crop_advisor": crop_advisor is not None,
            "alert_system": alert_system is not None,
            "analytics": analytics is not None,
        },
    }


# ============================================================
# EXISTING ENDPOINTS (backward compatible)
# ============================================================
@app.get("/commodities")
async def get_commodities():
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    commodities = price_loader.get_commodities_list()
    return {"commodities": commodities, "count": len(commodities)}


@app.get("/states")
async def get_states():
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    return {"states": price_loader.get_states_list(), "count": len(price_loader.states)}


@app.get("/markets/{state}")
async def get_markets(state: str):
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    markets = price_loader.get_markets_by_state(state)
    if not markets:
        raise HTTPException(status_code=404, detail=f"No markets found for: {state}")
    return {"state": state, "markets": markets, "count": len(markets)}


@app.get("/prices/{commodity}/{state}")
async def get_prices(commodity: str, state: str, limit: int = Query(20, ge=1, le=100)):
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    prices = price_loader.get_latest_prices(commodity, state, limit)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No prices for {commodity} in {state}")
    all_prices = [p["modal_price"] for p in prices]
    avg_price = sum(all_prices) / len(all_prices)
    return {
        "commodity": commodity,
        "state": state,
        "prices": prices,
        "stats": {
            "average_price": round(avg_price, 2),
            "min_price": min(all_prices),
            "max_price": max(all_prices),
            "markets_count": len(prices),
        },
    }


@app.get("/prices/history/{commodity}")
async def get_price_history(
    commodity: str,
    state: Optional[str] = Query(None),
    days: int = Query(90, ge=7, le=365),
):
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    df = price_loader.get_price_for_prediction(commodity, state or "", None)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No history for {commodity}")
    df = df.tail(days)
    history = [
        {"date": row["ds"].strftime("%Y-%m-%d"), "price": round(row["y"], 2)}
        for _, row in df.iterrows()
    ]
    return {"commodity": commodity, "state": state, "history": history, "days": len(history)}


# ============================================================
# LEGACY ENDPOINTS — Prophet-based (kept working)
# ============================================================
@app.post("/train")
async def train_model_legacy(request: TrainRequest):
    if not price_loader or not predictor_legacy:
        raise HTTPException(status_code=503, detail="Services not loaded")
    df = price_loader.get_price_for_prediction(request.commodity, request.state, request.market)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {request.commodity} in {request.state}")
    if len(df) < 30:
        raise HTTPException(status_code=400, detail=f"Need ≥30 records, got {len(df)}")
    success = predictor_legacy.train(df, request.commodity, request.state, request.market)
    if not success:
        raise HTTPException(status_code=500, detail="Training failed")
    return {"status": "success", "message": f"Prophet model trained for {request.commodity}", "data_points": len(df)}


@app.get("/predict/{commodity}/{state}")
async def predict_prices_legacy(
    commodity: str, state: str,
    market: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=14),
):
    if not predictor_legacy:
        raise HTTPException(status_code=503, detail="Legacy predictor not loaded")
    result = predictor_legacy.predict(commodity, state, market, days)
    if result is None:
        df = price_loader.get_price_for_prediction(commodity, state, market)
        if not df.empty and len(df) >= 30:
            predictor_legacy.train(df, commodity, state, market)
            result = predictor_legacy.predict(commodity, state, market, days)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No model for {commodity} in {state}")
    return result


@app.get("/recommend/{commodity}/{state}")
async def get_recommendation_legacy(
    commodity: str, state: str,
    current_price: float = Query(...),
    msp: Optional[float] = Query(None),
):
    if not predictor_legacy or not price_loader:
        raise HTTPException(status_code=503, detail="Services not loaded")
    result = predictor_legacy.predict(commodity, state, None, days=7)
    if result is None:
        df = price_loader.get_price_for_prediction(commodity, state, None)
        if not df.empty and len(df) >= 30:
            predictor_legacy.train(df, commodity, state, None)
            result = predictor_legacy.predict(commodity, state, None, days=7)
    if result is None or not result.get("predictions"):
        raise HTTPException(status_code=404, detail=f"Cannot generate recommendation")
    volatility = price_loader.get_price_volatility(commodity, state, days=30)
    recommendation = predictor_legacy.get_sell_recommendation(current_price, result["predictions"], volatility, msp)
    return {"commodity": commodity, "state": state, "current_price": current_price, **recommendation}


# ============================================================
# ANALYTICS ENDPOINTS (existing, kept)
# ============================================================
@app.get("/analytics/volatility/{commodity}/{state}")
async def get_volatility(commodity: str, state: str, days: int = Query(30, ge=7, le=90)):
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not loaded")
    result = analytics.calculate_volatility(commodity, state, days)
    return {"commodity": commodity, "state": state, "days_analyzed": days, **result}


@app.get("/analytics/trends/{commodity}/{state}")
async def get_trends(commodity: str, state: str, days: int = Query(30, ge=7, le=90)):
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not loaded")
    result = analytics.detect_trends(commodity, state, days)
    return {"commodity": commodity, "state": state, "days_analyzed": days, **result}


@app.get("/analytics/seasonal/{commodity}")
async def get_seasonal(commodity: str, state: Optional[str] = Query(None)):
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not loaded")
    result = analytics.find_seasonal_patterns(commodity, state)
    return {"commodity": commodity, "state": state, **result}


@app.get("/analytics/market-comparison/{commodity}/{state}")
async def get_market_comparison(commodity: str, state: str, top_n: int = Query(5, ge=3, le=10)):
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    result = price_loader.get_market_comparison(commodity, state, top_n)
    return {"commodity": commodity, "state": state, "markets": result, "count": len(result)}


@app.get("/analytics/top-performers/{state}")
async def get_top_performers(state: str, days: int = Query(30, ge=7, le=90), top_n: int = Query(5, ge=3, le=10)):
    if not price_loader:
        raise HTTPException(status_code=503, detail="Data not loaded")
    result = price_loader.get_top_performers(state, days, top_n)
    return {"state": state, "days_analyzed": days, **result}


@app.get("/analytics/insights/{commodity}/{state}")
async def get_insights(commodity: str, state: str, days: int = Query(30, ge=7, le=90)):
    if not analytics or not insights:
        raise HTTPException(status_code=503, detail="Services not loaded")
    market_data = analytics.get_market_insights(commodity, state, days)
    insight_texts = insights.generate_comprehensive_insights(commodity, state, market_data)
    return {
        "commodity": commodity, "state": state,
        "insights": insight_texts,
        "market_health": market_data.get("market_health"),
        "detailed_analytics": {
            "volatility": market_data.get("volatility"),
            "trends": market_data.get("trends"),
            "seasonal_patterns": market_data.get("seasonal_patterns"),
        },
    }


# ============================================================
# NEW ENDPOINTS — Multi-Model ML
# ============================================================
@app.post("/train-models")
async def train_models(request: TrainRequest):
    """Train all ML models (LR + RF + XGBoost) for a commodity/state."""
    if not trainer:
        raise HTTPException(status_code=503, detail="Trainer not loaded")

    raw_df = None
    if price_loader and price_loader.df is not None:
        raw_df = price_loader.df

    result = trainer.train_all_models(
        request.commodity, request.state, request.market, raw_df
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "status": "success",
        "message": f"3 models trained for {request.commodity} in {request.state}",
        "metrics": result["metrics"],
        "best_model": result["best_model"],
        "training_info": result["training_info"],
    }


@app.post("/predict-price")
async def predict_price(request: PredictRequest):
    """Get ensemble price predictions (XGB + RF + Prophet + LR)."""
    if not prediction_engine:
        raise HTTPException(status_code=503, detail="Prediction engine not loaded")

    raw_df = price_loader.df if price_loader and price_loader.df is not None else None

    # Auto-train if no models exist
    models = trainer.load_models(request.commodity, request.state)
    if not models:
        logger.info(f"Auto-training models for {request.commodity}/{request.state}...")
        train_result = trainer.train_all_models(
            request.commodity, request.state, request.market, raw_df
        )
        if "error" in train_result:
            raise HTTPException(status_code=400, detail=train_result["error"])

    result = prediction_engine.predict(
        request.commodity, request.state, request.days, raw_df
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Cannot predict for {request.commodity} in {request.state}",
        )

    return result


@app.get("/model-comparison/{commodity}/{state}")
async def model_comparison(commodity: str, state: str):
    """Compare model performance metrics (RMSE, MAE, R²)."""
    if not trainer:
        raise HTTPException(status_code=503, detail="Trainer not loaded")
    result = trainer.get_model_comparison(commodity, state)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No trained models for {commodity} in {state}. Train first via POST /train-models",
        )
    return result


@app.get("/recommendation/{commodity}/{state}")
async def get_recommendation(
    commodity: str,
    state: str,
    current_price: Optional[float] = Query(None),
    msp: Optional[float] = Query(None),
):
    """Get farmer-friendly sell/wait recommendation (bilingual)."""
    if not prediction_engine:
        raise HTTPException(status_code=503, detail="Engine not loaded")

    raw_df = price_loader.df if price_loader and price_loader.df is not None else None

    # Auto-train if needed
    models = trainer.load_models(commodity, state)
    if not models:
        trainer.train_all_models(commodity, state, None, raw_df)

    result = prediction_engine.get_recommendation(
        commodity, state, current_price, msp, raw_df
    )
    return result


# ============================================================
# NEW ENDPOINTS — Location Engine
# ============================================================
@app.post("/nearest-mandis")
async def nearest_mandis(request: NearestMandiRequest):
    """Find nearest mandis ranked by price + distance."""
    if not location_engine:
        raise HTTPException(status_code=503, detail="Location engine not loaded")

    try:
        # Get predicted prices if commodity specified
        predicted_prices = None
        if request.commodity and request.state:
            raw_df = price_loader.df if price_loader and price_loader.df is not None else None
            forecast = prediction_engine.predict(
                request.commodity, request.state, 1, raw_df
            )
            if forecast and forecast.get("predictions"):
                pred_price = forecast["predictions"][0]["predicted_price"]
                # Apply to all mandis in same state
                predicted_prices = {}
                if location_engine.mandis is not None:
                    for _, m in location_engine.mandis.iterrows():
                        predicted_prices[str(m.get("name", ""))] = pred_price

        result = location_engine.find_nearest_mandis(
            lat=request.latitude,
            lon=request.longitude,
            district=request.district,
            top_n=request.top_n,
            max_radius_km=request.max_radius_km,
            predicted_prices=predicted_prices,
        )

        return {
            "mandis": result,
            "count": len(result),
            "search_params": {
                "latitude": request.latitude,
                "longitude": request.longitude,
                "district": request.district,
                "radius_km": request.max_radius_km,
            },
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/mandis")
async def get_all_mandis():
    """Get all mandis for map display."""
    if not location_engine:
        raise HTTPException(status_code=503, detail="Location engine not loaded")
    mandis = location_engine.get_all_mandis()
    return {"mandis": mandis, "count": len(mandis)}


# ============================================================
# NEW ENDPOINTS — Crop Advisory
# ============================================================
@app.post("/crop-advisory")
async def get_crop_advisory(request: CropAdvisoryRequest):
    """Get harvest + price advisory for a crop."""
    if not crop_advisor:
        raise HTTPException(status_code=503, detail="Advisor not loaded")

    # If no predicted price given, try to compute one
    pred_price = request.predicted_price
    if pred_price is None and request.state:
        try:
            raw_df = price_loader.df if price_loader and price_loader.df is not None else None
            forecast = prediction_engine.predict(
                request.crop, request.state, 7, raw_df
            )
            if forecast and forecast.get("predictions"):
                pred_price = forecast["predictions"][-1]["predicted_price"]
        except Exception:
            pass

    result = crop_advisor.calculate_harvest_advisory(
        request.crop, request.sowing_date, pred_price
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.get("/crops")
async def get_crops():
    """List all crops with growth cycle data."""
    if not crop_advisor:
        raise HTTPException(status_code=503, detail="Advisor not loaded")
    return {
        "crops": crop_advisor.get_available_crops(),
        "count": len(crop_advisor.get_available_crops()),
    }


# ============================================================
# NEW ENDPOINTS — Alerts
# ============================================================
@app.post("/alerts/create")
async def create_alert(request: AlertCreateRequest):
    """Create a price alert (mock SMS/WhatsApp)."""
    if not alert_system:
        raise HTTPException(status_code=503, detail="Alert system not loaded")

    result = alert_system.create_alert(
        commodity=request.commodity,
        state=request.state,
        target_price=request.target_price,
        direction=request.direction,
        phone=request.phone,
        language=request.language,
        market=request.market,
    )
    return result


@app.get("/alerts")
async def get_alerts(active_only: bool = Query(True)):
    """List alerts."""
    if not alert_system:
        raise HTTPException(status_code=503, detail="Alert system not loaded")

    if active_only:
        alerts = alert_system.get_active_alerts()
    else:
        alerts = alert_system.get_all_alerts()

    return {"alerts": alerts, "count": len(alerts)}


# ============================================================
# Run
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
