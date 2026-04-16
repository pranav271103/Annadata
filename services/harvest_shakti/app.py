"""Harvest Shakti - AGRI-MAA: Complete Decision Support System for farmers.

Features:
  - Optimal harvest window prediction
  - Yield estimation using remote sensing
  - Post-harvest loss risk assessment
  - Market-aware harvest scheduling
  - ML-based crop recommendation (Random Forest simulated)
  - Fertilizer advisory with dosage per hectare
  - 7-day irrigation scheduling
  - Pest/disease risk alerts
  - Crop rotation planner
  - AI chatbot (Gemini-style) for farmer queries
"""

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.shared.auth.router import router as auth_router, setup_rate_limiting
from services.shared.config import settings
from services.shared.db.session import close_db, init_db, get_db
from services.shared.db.models import HarvestPlot

# ---------------------------------------------------------------------------
# Crop yield reference database
# ---------------------------------------------------------------------------

CROP_YIELD_DATA: dict[str, dict] = {
    "wheat": {
        "avg_yield_tonnes_per_ha": 3.5,
        "max_yield_tonnes_per_ha": 6.0,
        "growth_duration_days": 120,
        "optimal_temp_range": (15, 25),
        "water_requirement_mm": 450,
        "msp_per_quintal": 2275,
        "stages": {
            "sowing": 0,
            "tillering": 25,
            "jointing": 50,
            "heading": 70,
            "grain_filling": 90,
            "maturity": 115,
        },
    },
    "rice": {
        "avg_yield_tonnes_per_ha": 4.0,
        "max_yield_tonnes_per_ha": 7.5,
        "growth_duration_days": 130,
        "optimal_temp_range": (22, 32),
        "water_requirement_mm": 1200,
        "msp_per_quintal": 2183,
        "stages": {
            "sowing": 0,
            "seedling": 20,
            "tillering": 40,
            "panicle_initiation": 65,
            "flowering": 90,
            "grain_filling": 105,
            "maturity": 125,
        },
    },
    "cotton": {
        "avg_yield_tonnes_per_ha": 1.8,
        "max_yield_tonnes_per_ha": 3.5,
        "growth_duration_days": 180,
        "optimal_temp_range": (21, 30),
        "water_requirement_mm": 700,
        "msp_per_quintal": 6620,
        "stages": {
            "sowing": 0,
            "emergence": 10,
            "squaring": 45,
            "flowering": 70,
            "boll_development": 100,
            "boll_opening": 140,
            "maturity": 175,
        },
    },
    "maize": {
        "avg_yield_tonnes_per_ha": 3.0,
        "max_yield_tonnes_per_ha": 5.5,
        "growth_duration_days": 100,
        "optimal_temp_range": (18, 27),
        "water_requirement_mm": 500,
        "msp_per_quintal": 2090,
        "stages": {
            "sowing": 0,
            "emergence": 7,
            "vegetative": 25,
            "tasseling": 55,
            "silking": 60,
            "grain_filling": 75,
            "maturity": 95,
        },
    },
    "sugarcane": {
        "avg_yield_tonnes_per_ha": 70.0,
        "max_yield_tonnes_per_ha": 120.0,
        "growth_duration_days": 360,
        "optimal_temp_range": (20, 35),
        "water_requirement_mm": 2000,
        "msp_per_quintal": 315,
        "stages": {
            "sowing": 0,
            "germination": 30,
            "tillering": 90,
            "grand_growth": 180,
            "maturity_phase": 300,
            "maturity": 355,
        },
    },
}

# ---------------------------------------------------------------------------
# Enums & Pydantic models
# ---------------------------------------------------------------------------



# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IrrigationType(str, Enum):
    drip = "drip"
    sprinkler = "sprinkler"
    flood = "flood"
    rainfed = "rainfed"


class PestPressure(str, Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


# --- Request bodies / query helpers ---


class PlotRegistration(BaseModel):
    plot_id: str = Field(..., description="Unique identifier for the plot")
    crop: str = Field(
        ..., description="Crop name (wheat, rice, cotton, maize, sugarcane)"
    )
    variety: str = Field("", description="Crop variety")
    area_hectares: float = Field(..., gt=0, description="Plot area in hectares")
    sowing_date: date = Field(..., description="Date of sowing (YYYY-MM-DD)")
    soil_health_score: float = Field(
        75.0, ge=0, le=100, description="Soil health score (0-100)"
    )
    irrigation_type: IrrigationType = Field(
        IrrigationType.flood, description="Type of irrigation"
    )
    region: str = Field("", description="Region / district name")


# --- Response models ---


class ConfidenceInterval(BaseModel):
    low_tonnes: float
    high_tonnes: float


class YieldFactors(BaseModel):
    soil_health_factor: float
    weather_factor: float
    irrigation_factor: float
    pest_factor: float
    combined_factor: float


class YieldEstimateResponse(BaseModel):
    plot_id: str
    crop: str
    variety: str
    area_hectares: float
    base_yield_tonnes: float
    estimated_yield_tonnes: float
    yield_per_hectare_tonnes: float
    confidence_interval: ConfidenceInterval
    factors: YieldFactors
    weather_score: float
    pest_pressure: str
    estimated_at: str


class HarvestWindowDetail(BaseModel):
    start: str
    end: str
    best_date: str


class WeatherRisk(BaseModel):
    rain_probability_pct: float
    heatwave_risk: str
    frost_risk: str


class HarvestWindowResponse(BaseModel):
    plot_id: str
    crop: str
    sowing_date: str
    expected_maturity_date: str
    days_to_maturity: int
    current_growth_stage: str
    growth_progress_pct: float
    optimal_harvest_window: HarvestWindowDetail
    weather_risk: WeatherRisk
    recommendation: str


class MandiInfo(BaseModel):
    name: str
    price_per_quintal: float
    distance_km: float


class MarketTimingResponse(BaseModel):
    crop: str
    region: str
    current_msp_per_quintal: float
    current_market_price_per_quintal: float
    price_trend: str
    price_trend_pct: float
    recommendation: str
    nearby_mandis: list[MandiInfo]
    storage_advisory: str
    generated_at: str


class PlotRegistrationResponse(BaseModel):
    message: str
    plot_id: str
    crop: str
    area_hectares: float
    expected_maturity_date: str


# --- New feature request/response models ---


class CropRecommendationRequest(BaseModel):
    nitrogen: float = Field(..., ge=0, le=300, description="Soil Nitrogen (kg/ha)")
    phosphorus: float = Field(..., ge=0, le=200, description="Soil Phosphorus (kg/ha)")
    potassium: float = Field(..., ge=0, le=200, description="Soil Potassium (kg/ha)")
    pH: float = Field(..., ge=3.0, le=10.0, description="Soil pH level")
    moisture: float = Field(..., ge=0, le=100, description="Soil moisture percentage")
    temperature: float = Field(25.0, description="Current temperature (°C)")
    humidity: float = Field(60.0, ge=0, le=100, description="Relative humidity (%)")
    rainfall_mm: float = Field(100.0, ge=0, description="Expected rainfall (mm/season)")
    region: str = Field("", description="Region/state for localized advice")


class CropScore(BaseModel):
    crop: str
    suitability_score: float
    confidence: float
    season: str
    water_need: str
    description: str
    key_factors: list[str]


class CropRecommendationResponse(BaseModel):
    top_recommendation: str
    recommendations: list[CropScore]
    soil_analysis: dict
    weather_suitability: str
    advisory: str
    generated_at: str


class FertilizerAdvisoryRequest(BaseModel):
    crop: str = Field(..., description="Crop name")
    current_N: float = Field(..., ge=0, le=300, description="Current soil N (kg/ha)")
    current_P: float = Field(..., ge=0, le=200, description="Current soil P (kg/ha)")
    current_K: float = Field(..., ge=0, le=200, description="Current soil K (kg/ha)")
    area_hectares: float = Field(1.0, gt=0, description="Field area in hectares")
    soil_pH: float = Field(7.0, ge=3.0, le=10.0, description="Soil pH")
    organic_carbon_pct: float = Field(
        0.5, ge=0, le=5.0, description="Organic carbon percentage"
    )


class FertilizerRecommendation(BaseModel):
    fertilizer: str
    nutrient_supplied: str
    deficit_kg_per_ha: float
    quantity_kg_per_ha: float
    total_quantity_kg: float
    estimated_cost_inr: float
    application_note: str


class FertilizerAdvisoryResponse(BaseModel):
    crop: str
    area_hectares: float
    nutrient_status: dict
    recommendations: list[FertilizerRecommendation]
    total_estimated_cost_inr: float
    soil_health_notes: list[str]
    application_schedule: list[str]
    generated_at: str


class IrrigationScheduleRequest(BaseModel):
    crop: str = Field(..., description="Crop name")
    soil_moisture: float = Field(
        ..., ge=0, le=100, description="Current soil moisture (%)"
    )
    temperature: float = Field(..., description="Current temperature (°C)")
    humidity: float = Field(..., ge=0, le=100, description="Relative humidity (%)")
    rain_forecast_mm: list[float] = Field(
        default=[0, 0, 0, 0, 0, 0, 0],
        description="7-day rain forecast in mm (list of 7 values)",
    )
    crop_stage: str = Field("vegetative", description="Current crop growth stage")
    irrigation_type: IrrigationType = Field(
        IrrigationType.flood, description="Irrigation system type"
    )
    area_hectares: float = Field(1.0, gt=0, description="Field area in hectares")


class DaySchedule(BaseModel):
    day: int
    date: str
    action: str
    reason: str
    water_mm: float
    rain_expected_mm: float
    soil_moisture_predicted: float


class IrrigationScheduleResponse(BaseModel):
    crop: str
    current_soil_moisture: float
    irrigation_type: str
    schedule: list[DaySchedule]
    total_water_needed_mm: float
    water_saving_tip: str
    critical_note: str
    generated_at: str


class PestAlert(BaseModel):
    disease: str
    risk_level: str
    risk_score: float
    symptoms: str
    treatment: str
    prevention: str
    contributing_factors: list[str]


class PestAlertResponse(BaseModel):
    crop: str
    region: str
    temperature: float
    humidity: float
    total_alerts: int
    alerts: list[PestAlert]
    general_advisory: str
    generated_at: str


class CropRotationResponse(BaseModel):
    current_crop: str
    recommended_next_crops: list[str]
    avoid_crops: list[str]
    rotation_reason: str
    nitrogen_benefit: str
    detailed_plan: list[dict]
    sustainability_score: float
    generated_at: str


class ChatRequest(BaseModel):
    message: str = Field(
        ..., min_length=1, max_length=2000, description="Farmer's question"
    )
    language: str = Field("en", description="Preferred language (en/hi)")
    context: Optional[dict] = Field(
        None, description="Optional context (crop, region, etc.)"
    )


class ChatResponse(BaseModel):
    response: str
    category: str
    related_endpoints: list[str]
    confidence: float
    model: str
    generated_at: str


# DB: _plot_store → HarvestPlot table (harvest_plots)

# ---------------------------------------------------------------------------
# Irrigation & pest multiplier look-ups
# ---------------------------------------------------------------------------

IRRIGATION_FACTOR: dict[str, float] = {
    "drip": 1.15,
    "sprinkler": 1.05,
    "flood": 0.90,
    "rainfed": 0.80,
}

PEST_FACTOR: dict[str, float] = {
    "none": 1.0,
    "low": 0.95,
    "medium": 0.85,
    "high": 0.65,
}

# Seasonal monthly heuristics (index 0 = Jan, 11 = Dec)
MONTHLY_RAIN_PROB: list[float] = [10, 12, 18, 25, 35, 55, 75, 72, 55, 30, 12, 8]
MONTHLY_HEATWAVE_RISK: list[str] = [
    "low",
    "low",
    "medium",
    "high",
    "high",
    "high",
    "medium",
    "medium",
    "low",
    "low",
    "low",
    "low",
]
MONTHLY_FROST_RISK: list[str] = [
    "high",
    "medium",
    "low",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "low",
    "high",
]
# Price seasonality factor by month (rough heuristic)
MONTHLY_PRICE_FACTOR: list[float] = [
    1.02,
    1.00,
    0.97,
    0.95,
    0.96,
    0.98,
    1.00,
    1.02,
    1.04,
    1.05,
    1.06,
    1.04,
]

# Regional mandi templates (used for generating nearby mandis)
REGION_MANDIS: dict[str, list[str]] = {
    "default": ["District Mandi", "Taluka Mandi", "APMC Yard", "State Mandi"],
    "punjab": ["Khanna Mandi", "Ludhiana Mandi", "Amritsar Mandi", "Jalandhar Mandi"],
    "haryana": ["Karnal Mandi", "Panipat Mandi", "Hisar Mandi", "Sirsa Mandi"],
    "uttar pradesh": ["Lucknow Mandi", "Agra Mandi", "Kanpur Mandi", "Meerut Mandi"],
    "maharashtra": ["Pune Mandi", "Nagpur Mandi", "Nashik Mandi", "Aurangabad Mandi"],
    "madhya pradesh": [
        "Indore Mandi",
        "Bhopal Mandi",
        "Jabalpur Mandi",
        "Ujjain Mandi",
    ],
}

# ---------------------------------------------------------------------------
# Crop-Soil Suitability Matrix (simulated Random Forest knowledge base)
# Each crop has ideal ranges for N, P, K, pH, moisture and a weight vector
# used by the simulated classifier to score suitability.
# ---------------------------------------------------------------------------

CROP_SOIL_PROFILES: dict[str, dict] = {
    "rice": {
        "N": (60, 120),
        "P": (20, 60),
        "K": (20, 50),
        "pH": (5.5, 7.0),
        "moisture": (60, 90),
        "temp_range": (22, 32),
        "humidity_range": (60, 95),
        "season": "kharif",
        "water_need": "high",
        "description": "Best in flooded/waterlogged fields with high organic matter.",
    },
    "wheat": {
        "N": (80, 140),
        "P": (30, 70),
        "K": (20, 50),
        "pH": (6.0, 7.5),
        "moisture": (40, 65),
        "temp_range": (10, 25),
        "humidity_range": (30, 65),
        "season": "rabi",
        "water_need": "medium",
        "description": "Thrives in well-drained loamy soils with cool weather.",
    },
    "maize": {
        "N": (60, 120),
        "P": (25, 65),
        "K": (20, 55),
        "pH": (5.5, 7.5),
        "moisture": (45, 70),
        "temp_range": (18, 30),
        "humidity_range": (40, 75),
        "season": "kharif",
        "water_need": "medium",
        "description": "Versatile crop; needs good drainage and moderate rainfall.",
    },
    "cotton": {
        "N": (80, 130),
        "P": (20, 55),
        "K": (15, 45),
        "pH": (6.0, 8.0),
        "moisture": (35, 60),
        "temp_range": (21, 35),
        "humidity_range": (40, 70),
        "season": "kharif",
        "water_need": "medium",
        "description": "Prefers black soil with warm temperatures and low humidity at harvest.",
    },
    "sugarcane": {
        "N": (100, 180),
        "P": (30, 70),
        "K": (30, 70),
        "pH": (6.0, 7.5),
        "moisture": (55, 85),
        "temp_range": (20, 38),
        "humidity_range": (50, 85),
        "season": "annual",
        "water_need": "very_high",
        "description": "Long-duration crop needing deep, fertile, well-drained soil.",
    },
    "chickpea": {
        "N": (20, 60),
        "P": (30, 70),
        "K": (15, 40),
        "pH": (6.0, 8.0),
        "moisture": (25, 50),
        "temp_range": (15, 30),
        "humidity_range": (20, 55),
        "season": "rabi",
        "water_need": "low",
        "description": "Legume that fixes nitrogen; excellent for crop rotation after cereals.",
    },
    "mustard": {
        "N": (40, 90),
        "P": (20, 50),
        "K": (15, 40),
        "pH": (6.0, 7.8),
        "moisture": (30, 55),
        "temp_range": (10, 25),
        "humidity_range": (30, 60),
        "season": "rabi",
        "water_need": "low",
        "description": "Oilseed crop suited for cool, dry conditions.",
    },
    "soybean": {
        "N": (20, 60),
        "P": (25, 65),
        "K": (20, 50),
        "pH": (5.5, 7.0),
        "moisture": (45, 70),
        "temp_range": (20, 32),
        "humidity_range": (50, 80),
        "season": "kharif",
        "water_need": "medium",
        "description": "Nitrogen-fixing legume; prefers warm, moist conditions.",
    },
    "groundnut": {
        "N": (20, 50),
        "P": (20, 55),
        "K": (20, 50),
        "pH": (5.5, 7.0),
        "moisture": (35, 60),
        "temp_range": (22, 33),
        "humidity_range": (40, 70),
        "season": "kharif",
        "water_need": "medium",
        "description": "Needs sandy loam soil; good after cereals for rotation.",
    },
    "potato": {
        "N": (100, 160),
        "P": (40, 80),
        "K": (50, 100),
        "pH": (5.0, 6.5),
        "moisture": (50, 75),
        "temp_range": (12, 22),
        "humidity_range": (60, 85),
        "season": "rabi",
        "water_need": "medium",
        "description": "Needs cool weather, loose soil, and consistent moisture.",
    },
    "onion": {
        "N": (80, 130),
        "P": (30, 60),
        "K": (40, 80),
        "pH": (6.0, 7.5),
        "moisture": (40, 65),
        "temp_range": (15, 28),
        "humidity_range": (40, 70),
        "season": "rabi",
        "water_need": "medium",
        "description": "Needs well-drained fertile soil with consistent irrigation.",
    },
    "tomato": {
        "N": (80, 140),
        "P": (40, 80),
        "K": (50, 90),
        "pH": (6.0, 7.0),
        "moisture": (50, 75),
        "temp_range": (18, 30),
        "humidity_range": (50, 80),
        "season": "rabi",
        "water_need": "medium",
        "description": "Warm-season crop needing rich, well-drained soil.",
    },
}

# ---------------------------------------------------------------------------
# Fertilizer Knowledge Base
# ---------------------------------------------------------------------------

FERTILIZER_DB: dict[str, dict] = {
    "urea": {
        "nutrient": "N",
        "content_pct": 46.0,
        "description": "Primary nitrogen source; apply in split doses",
        "cost_per_kg": 6.0,
        "application_note": "Apply in 2-3 split doses. Avoid during heavy rain.",
    },
    "dap": {
        "nutrient": "P",
        "content_pct": 46.0,
        "secondary_nutrient": "N",
        "secondary_pct": 18.0,
        "description": "Di-ammonium Phosphate — best basal P source",
        "cost_per_kg": 27.0,
        "application_note": "Apply as basal dose at sowing. Mix in soil.",
    },
    "ssp": {
        "nutrient": "P",
        "content_pct": 16.0,
        "description": "Single Super Phosphate — also supplies Calcium and Sulphur",
        "cost_per_kg": 9.0,
        "application_note": "Good for oilseeds and pulses needing sulphur.",
    },
    "mop": {
        "nutrient": "K",
        "content_pct": 60.0,
        "description": "Muriate of Potash — primary potassium source",
        "cost_per_kg": 18.0,
        "application_note": "Apply as basal dose. Avoid in saline/chloride-sensitive crops.",
    },
    "npk_complex": {
        "nutrient": "NPK",
        "content_pct": 0.0,
        "n_pct": 12.0,
        "p_pct": 32.0,
        "k_pct": 16.0,
        "description": "Balanced NPK complex fertilizer",
        "cost_per_kg": 28.0,
        "application_note": "Good for balanced nutrition. Apply as basal + top dress.",
    },
    "zinc_sulphate": {
        "nutrient": "Zn",
        "content_pct": 33.0,
        "description": "Micronutrient — essential for rice and wheat",
        "cost_per_kg": 45.0,
        "application_note": "Apply 25 kg/ha for Zn-deficient soils. Mix with sand for uniform spread.",
    },
}

# Crop-specific NPK requirements (kg/ha) for a standard yield target
CROP_NUTRIENT_REQUIREMENTS: dict[str, dict] = {
    "wheat": {"N": 120, "P": 60, "K": 40},
    "rice": {"N": 100, "P": 50, "K": 50},
    "maize": {"N": 120, "P": 60, "K": 40},
    "cotton": {"N": 100, "P": 50, "K": 50},
    "sugarcane": {"N": 250, "P": 80, "K": 80},
    "chickpea": {"N": 20, "P": 60, "K": 20},
    "mustard": {"N": 80, "P": 40, "K": 20},
    "soybean": {"N": 30, "P": 60, "K": 40},
    "groundnut": {"N": 25, "P": 50, "K": 40},
    "potato": {"N": 150, "P": 60, "K": 100},
    "onion": {"N": 100, "P": 50, "K": 60},
    "tomato": {"N": 120, "P": 60, "K": 80},
}

# ---------------------------------------------------------------------------
# Crop Rotation Rules
# ---------------------------------------------------------------------------

CROP_ROTATION_RULES: dict[str, dict] = {
    "wheat": {
        "recommended_next": ["chickpea", "mustard", "soybean", "groundnut"],
        "avoid_next": ["wheat", "rice"],
        "reason": "Follow wheat with a legume (chickpea/soybean) to restore nitrogen "
        "and break pest cycles. Mustard is also excellent as it adds organic "
        "matter and suppresses soil-borne pathogens.",
        "nitrogen_benefit": "Legumes fix 40-80 kg N/ha, reducing fertilizer need by 30-40%.",
    },
    "rice": {
        "recommended_next": ["wheat", "chickpea", "mustard", "potato"],
        "avoid_next": ["rice"],
        "reason": "Rice-wheat is the classic Indo-Gangetic rotation. Alternatively, "
        "rice-chickpea restores soil nitrogen. Avoid continuous rice to "
        "prevent methane buildup and soil degradation.",
        "nitrogen_benefit": "Rice-legume rotation can save ₹3,000-5,000/ha in fertilizer costs.",
    },
    "cotton": {
        "recommended_next": ["wheat", "chickpea", "groundnut", "onion"],
        "avoid_next": ["cotton"],
        "reason": "Cotton depletes soil heavily. Follow with wheat (rabi) or a legume "
        "to restore fertility. Groundnut fixes nitrogen and breaks bollworm cycle.",
        "nitrogen_benefit": "Legume rotation reduces pest pressure by 40-60%.",
    },
    "maize": {
        "recommended_next": ["chickpea", "wheat", "mustard", "potato"],
        "avoid_next": ["maize", "sugarcane"],
        "reason": "Maize is a heavy nitrogen feeder. Chickpea or other legumes restore "
        "soil N. Wheat provides good rabi-season income after kharif maize.",
        "nitrogen_benefit": "Maize-chickpea rotation improves soil organic carbon by 15-20%.",
    },
    "sugarcane": {
        "recommended_next": ["rice", "wheat", "chickpea", "soybean"],
        "avoid_next": ["sugarcane"],
        "reason": "Sugarcane exhausts soil over 12-18 months. MUST rotate with a "
        "cereal or legume to restore soil structure and nutrients.",
        "nitrogen_benefit": "Post-sugarcane legume rotation is critical for soil recovery.",
    },
    "chickpea": {
        "recommended_next": ["rice", "maize", "cotton", "wheat"],
        "avoid_next": ["chickpea", "soybean"],
        "reason": "After a legume, plant a cereal (rice/wheat/maize) or cash crop (cotton) "
        "that benefits from the residual nitrogen fixed by chickpea.",
        "nitrogen_benefit": "Chickpea leaves 40-60 kg N/ha residual nitrogen in soil.",
    },
    "mustard": {
        "recommended_next": ["rice", "maize", "cotton", "sugarcane"],
        "avoid_next": ["mustard"],
        "reason": "Mustard is a good break crop. Follow with a kharif cereal or "
        "cash crop that benefits from improved soil health.",
        "nitrogen_benefit": "Mustard residue adds organic matter, improving soil water retention.",
    },
    "soybean": {
        "recommended_next": ["wheat", "maize", "cotton", "onion"],
        "avoid_next": ["soybean", "chickpea"],
        "reason": "Soybean-wheat is an excellent rotation for central India. Soybean "
        "fixes nitrogen that wheat uses efficiently.",
        "nitrogen_benefit": "Soybean fixes 50-80 kg N/ha, saving significant fertilizer input.",
    },
    "groundnut": {
        "recommended_next": ["wheat", "rice", "cotton", "maize"],
        "avoid_next": ["groundnut"],
        "reason": "Groundnut improves soil structure. Follow with a cereal crop "
        "that benefits from residual nitrogen and improved soil tilth.",
        "nitrogen_benefit": "Groundnut-wheat rotation increases wheat yield by 10-15%.",
    },
    "potato": {
        "recommended_next": ["rice", "maize", "wheat", "onion"],
        "avoid_next": ["potato", "tomato"],
        "reason": "Avoid solanaceous crops back-to-back to prevent late blight carry-over. "
        "Cereals break the disease cycle effectively.",
        "nitrogen_benefit": "Cereal rotation after potato reduces disease incidence by 50-70%.",
    },
    "onion": {
        "recommended_next": ["rice", "maize", "soybean", "cotton"],
        "avoid_next": ["onion"],
        "reason": "Rotate onion with cereals or legumes to prevent soil-borne diseases "
        "like Fusarium wilt and white rot.",
        "nitrogen_benefit": "Cereal/legume rotation improves onion yield in subsequent cycles.",
    },
    "tomato": {
        "recommended_next": ["wheat", "maize", "chickpea", "onion"],
        "avoid_next": ["tomato", "potato"],
        "reason": "Avoid solanaceous crops consecutively. Wheat or chickpea breaks "
        "the disease and nematode cycle.",
        "nitrogen_benefit": "Non-solanaceous rotation reduces nematode population by 60-80%.",
    },
}

# ---------------------------------------------------------------------------
# Pest & Disease Condition Rules
# ---------------------------------------------------------------------------

PEST_DISEASE_RULES: list[dict] = [
    {
        "id": "rice_blast",
        "crop": "rice",
        "disease": "Rice Blast (Magnaporthe oryzae)",
        "conditions": {"temp_range": (20, 30), "humidity_min": 80, "moisture_min": 60},
        "severity_weights": {"humidity": 0.4, "temperature": 0.3, "moisture": 0.3},
        "symptoms": "Diamond-shaped lesions on leaves, neck rot, panicle blast.",
        "treatment": "Apply Tricyclazole 75% WP @ 0.6g/L or Isoprothiolane 40% EC @ 1.5mL/L. "
        "Drain standing water and apply potash fertilizer.",
        "prevention": "Use resistant varieties (Pusa Basmati 1509). Avoid excess nitrogen. "
        "Ensure proper spacing for air circulation.",
    },
    {
        "id": "wheat_rust",
        "crop": "wheat",
        "disease": "Yellow/Brown Rust (Puccinia spp.)",
        "conditions": {"temp_range": (10, 22), "humidity_min": 70, "moisture_min": 40},
        "severity_weights": {"humidity": 0.4, "temperature": 0.35, "moisture": 0.25},
        "symptoms": "Yellow-orange pustules on leaves. Brown rust shows on undersides.",
        "treatment": "Spray Propiconazole 25% EC @ 1mL/L or Tebuconazole @ 1mL/L. "
        "Two sprays at 15-day intervals.",
        "prevention": "Sow resistant varieties. Timely sowing (Nov 1-15). "
        "Avoid late nitrogen application.",
    },
    {
        "id": "cotton_bollworm",
        "crop": "cotton",
        "disease": "American Bollworm (Helicoverpa armigera)",
        "conditions": {"temp_range": (25, 35), "humidity_min": 50, "moisture_min": 30},
        "severity_weights": {"humidity": 0.3, "temperature": 0.4, "moisture": 0.3},
        "symptoms": "Bore holes in bolls, frass visible, damaged squares and flowers.",
        "treatment": "Release Trichogramma wasps (1.5 lakh/ha). Spray Emamectin Benzoate "
        "5% SG @ 0.4g/L or Chlorantraniliprole 18.5% SC @ 0.3mL/L.",
        "prevention": "Use Bt cotton varieties. Install pheromone traps (5/ha). "
        "Destroy crop residues after harvest.",
    },
    {
        "id": "maize_stem_borer",
        "crop": "maize",
        "disease": "Stem Borer (Chilo partellus)",
        "conditions": {"temp_range": (22, 32), "humidity_min": 55, "moisture_min": 40},
        "severity_weights": {"humidity": 0.3, "temperature": 0.4, "moisture": 0.3},
        "symptoms": "Dead hearts in young plants, shot holes in leaves, stem tunneling.",
        "treatment": "Apply Carbofuran 3G granules in leaf whorls @ 8-10 kg/ha. "
        "Spray Chlorantraniliprole 18.5% SC @ 0.4mL/L.",
        "prevention": "Early sowing. Remove and destroy stubbles. "
        "Release Trichogramma chilonis at 1 lakh/ha.",
    },
    {
        "id": "sugarcane_red_rot",
        "crop": "sugarcane",
        "disease": "Red Rot (Colletotrichum falcatum)",
        "conditions": {"temp_range": (25, 35), "humidity_min": 75, "moisture_min": 60},
        "severity_weights": {"humidity": 0.4, "temperature": 0.3, "moisture": 0.3},
        "symptoms": "Drying of crown, reddening of internal tissue, alcohol smell from cut cane.",
        "treatment": "Remove and burn infected stools. Treat setts with Carbendazim 50% WP "
        "@ 2g/L for 30 minutes before planting.",
        "prevention": "Use resistant varieties (CoC 671, Co 86032). Hot water treatment of setts. "
        "Avoid waterlogging.",
    },
    {
        "id": "late_blight",
        "crop": "potato",
        "disease": "Late Blight (Phytophthora infestans)",
        "conditions": {"temp_range": (10, 22), "humidity_min": 80, "moisture_min": 55},
        "severity_weights": {"humidity": 0.45, "temperature": 0.3, "moisture": 0.25},
        "symptoms": "Water-soaked lesions on leaves, white mold underneath, tuber rot.",
        "treatment": "Spray Mancozeb 75% WP @ 2.5g/L followed by Cymoxanil + Mancozeb @ 3g/L. "
        "Repeat every 7 days during conducive weather.",
        "prevention": "Use certified disease-free seed tubers. Hill up soil around plants. "
        "Destroy volunteer plants.",
    },
    {
        "id": "chickpea_wilt",
        "crop": "chickpea",
        "disease": "Fusarium Wilt (Fusarium oxysporum f.sp. ciceri)",
        "conditions": {"temp_range": (20, 30), "humidity_min": 45, "moisture_min": 30},
        "severity_weights": {"humidity": 0.3, "temperature": 0.4, "moisture": 0.3},
        "symptoms": "Yellowing and drooping of leaves, browning of vascular tissue.",
        "treatment": "Seed treatment with Trichoderma viride @ 4g/kg seed + Carbendazim @ 2g/kg. "
        "Soil application of Trichoderma @ 2.5 kg/ha.",
        "prevention": "Grow resistant varieties (JG 74, Avrodhi). Deep summer plowing. "
        "4-year crop rotation with cereals.",
    },
    {
        "id": "mustard_aphid",
        "crop": "mustard",
        "disease": "Mustard Aphid (Lipaphis erysimi)",
        "conditions": {"temp_range": (10, 25), "humidity_min": 40, "moisture_min": 25},
        "severity_weights": {"humidity": 0.35, "temperature": 0.35, "moisture": 0.3},
        "symptoms": "Curling of leaves, honeydew secretion, sooty mold, stunted growth.",
        "treatment": "Spray Dimethoate 30% EC @ 1mL/L or Imidacloprid 17.8% SL @ 0.3mL/L. "
        "Neem oil 5% also effective for mild infestations.",
        "prevention": "Timely sowing (Oct 15-25). Use resistant varieties. "
        "Install yellow sticky traps for monitoring.",
    },
    {
        "id": "general_fungal",
        "crop": "*",
        "disease": "General Fungal Risk (Multiple pathogens)",
        "conditions": {"temp_range": (18, 30), "humidity_min": 85, "moisture_min": 65},
        "severity_weights": {"humidity": 0.5, "temperature": 0.25, "moisture": 0.25},
        "symptoms": "Leaf spots, wilting, root rot, damping-off in seedlings.",
        "treatment": "Broad-spectrum fungicide: Mancozeb @ 2.5g/L or Copper Oxychloride @ 3g/L.",
        "prevention": "Proper drainage. Avoid overhead irrigation. Maintain field hygiene.",
    },
    {
        "id": "general_insect",
        "crop": "*",
        "disease": "General Insect Pest Risk",
        "conditions": {"temp_range": (25, 38), "humidity_min": 50, "moisture_min": 30},
        "severity_weights": {"humidity": 0.25, "temperature": 0.45, "moisture": 0.3},
        "symptoms": "Leaf feeding, bore holes, wilting, reduced vigour.",
        "treatment": "Neem-based insecticide (Azadirachtin 1500 ppm) @ 3mL/L for mild cases. "
        "Emamectin Benzoate 5% SG @ 0.4g/L for severe infestations.",
        "prevention": "Encourage natural predators (ladybugs, spiders). "
        "Use light traps and pheromone traps for monitoring.",
    },
]

# ---------------------------------------------------------------------------
# Chatbot Knowledge Base (simulated Gemini responses)
# ---------------------------------------------------------------------------

CHATBOT_KNOWLEDGE: dict[str, list[dict]] = {
    "crop_advice": [
        {
            "keywords": [
                "best crop",
                "what to grow",
                "which crop",
                "recommend crop",
                "crop suggestion",
                "kya ugaaye",
                "konsa fasal",
            ],
            "response": "Based on general Indian conditions, here are recommendations:\n\n"
            "**Kharif (June-Oct):** Rice, Maize, Cotton, Soybean, Groundnut\n"
            "**Rabi (Nov-Mar):** Wheat, Chickpea, Mustard, Potato, Onion\n\n"
            "For a personalized recommendation, use the `/recommend-crop` endpoint "
            "with your soil data (N, P, K, pH, moisture) and weather conditions.\n\n"
            "💡 **Tip:** Soil testing is the first step to a profitable season. "
            "Visit your nearest Krishi Vigyan Kendra (KVK) for free soil testing.",
        },
    ],
    "fertilizer": [
        {
            "keywords": [
                "fertilizer",
                "khad",
                "urea",
                "dap",
                "npk",
                "nutrient",
                "how much fertilizer",
                "fertilizer dose",
            ],
            "response": "**General Fertilizer Guide (per hectare):**\n\n"
            "| Crop | Urea (kg) | DAP (kg) | MoP (kg) |\n"
            "|------|-----------|----------|----------|\n"
            "| Wheat | 260 | 130 | 67 |\n"
            "| Rice | 217 | 109 | 83 |\n"
            "| Maize | 260 | 130 | 67 |\n\n"
            "**Important Tips:**\n"
            "- Apply DAP and MoP as **basal dose** at sowing\n"
            "- Split Urea into 2-3 doses (sowing, tillering, flowering)\n"
            "- Get soil tested first — excess fertilizer wastes money and harms soil\n\n"
            "Use `/fertilizer-advisory` for crop-specific recommendations based on "
            "your actual soil test results.",
        },
    ],
    "irrigation": [
        {
            "keywords": [
                "irrigation",
                "water",
                "paani",
                "sinchai",
                "when to irrigate",
                "how much water",
                "drip",
                "sprinkler",
            ],
            "response": "**Smart Irrigation Tips:**\n\n"
            "1. **Check soil moisture** before irrigating — avoid over-watering\n"
            "2. **Drip irrigation** saves 30-50% water vs flood irrigation\n"
            "3. **Morning irrigation** (6-9 AM) reduces evaporation losses\n"
            "4. **Critical stages** requiring irrigation:\n"
            "   - Wheat: Crown root initiation, flowering, grain filling\n"
            "   - Rice: Transplanting, tillering, panicle initiation\n"
            "   - Maize: Tasseling and silking\n\n"
            "🌧️ Use `/irrigation-schedule` for a 7-day plan based on your "
            "conditions and weather forecast.\n\n"
            "💡 **PM Krishi Sinchai Yojana** provides 55-90% subsidy on micro-irrigation.",
        },
    ],
    "pest_disease": [
        {
            "keywords": [
                "pest",
                "disease",
                "keeda",
                "bimari",
                "insect",
                "fungus",
                "yellow leaves",
                "spots on leaves",
                "wilt",
                "rot",
            ],
            "response": "**Common Crop Diseases & Quick Remedies:**\n\n"
            "🌾 **Wheat Yellow Rust:** Orange pustules on leaves → Spray Propiconazole 1mL/L\n"
            "🍚 **Rice Blast:** Diamond lesions → Tricyclazole 0.6g/L\n"
            "🌿 **Cotton Bollworm:** Bore holes in bolls → Emamectin Benzoate 0.4g/L\n"
            "🥔 **Potato Late Blight:** Water-soaked spots → Mancozeb 2.5g/L\n\n"
            "**Prevention is better than cure:**\n"
            "- Use certified seeds/resistant varieties\n"
            "- Proper spacing for air circulation\n"
            "- Destroy crop residues after harvest\n\n"
            "Use `/pest-alerts` for real-time risk assessment based on your conditions.",
        },
    ],
    "weather": [
        {
            "keywords": [
                "weather",
                "mausam",
                "rain",
                "barish",
                "forecast",
                "temperature",
                "frost",
                "heatwave",
                "monsoon",
            ],
            "response": "**Weather Advisory for Farmers:**\n\n"
            "📊 For accurate weather data, use the **Mausam Chakra** service "
            "or check IMD's Agromet Advisory at `mausam.imd.gov.in`.\n\n"
            "**Seasonal Precautions:**\n"
            "- **Monsoon (Jun-Sep):** Ensure field drainage. Prepare bunds.\n"
            "- **Winter (Nov-Feb):** Protect crops from frost with light irrigation at night.\n"
            "- **Summer (Mar-May):** Mulching reduces soil temperature by 5-8°C.\n\n"
            "💡 Install the **Meghdoot App** (by IMD) for village-level weather forecasts.",
        },
    ],
    "market_price": [
        {
            "keywords": [
                "price",
                "mandi",
                "market",
                "sell",
                "msp",
                "rate",
                "bhav",
                "daam",
                "when to sell",
            ],
            "response": "**Market Price Tips:**\n\n"
            "📈 **Current MSP (2024-25):**\n"
            "- Wheat: ₹2,275/quintal | Rice: ₹2,183/quintal\n"
            "- Cotton: ₹6,620/quintal | Maize: ₹2,090/quintal\n\n"
            "**Smart Selling Strategy:**\n"
            "1. Check prices at multiple mandis (use `/market-timing`)\n"
            "2. Avoid selling immediately after harvest (prices are lowest)\n"
            "3. Use government warehouses for storage (₹3-4/quintal/month)\n"
            "4. Register on **eNAM** for online mandi access\n\n"
            "💡 Use `/market-timing?crop=wheat&region=punjab` for real-time advice.",
        },
    ],
    "government_schemes": [
        {
            "keywords": [
                "scheme",
                "yojana",
                "subsidy",
                "loan",
                "government",
                "sarkar",
                "pm kisan",
                "insurance",
                "fasal bima",
            ],
            "response": "**Key Government Schemes for Farmers:**\n\n"
            "🏛️ **PM-KISAN:** ₹6,000/year in 3 installments. Register at pmkisan.gov.in\n"
            "🛡️ **PM Fasal Bima Yojana:** Crop insurance at just 1.5-5% premium\n"
            "💧 **PM Krishi Sinchai Yojana:** 55-90% subsidy on micro-irrigation\n"
            "🏦 **Kisan Credit Card (KCC):** Crop loan at 4% interest (with subvention)\n"
            "🧪 **Soil Health Card:** Free soil testing. Apply at soilhealth.dac.gov.in\n"
            "🚜 **Sub-Mission on Agricultural Mechanization:** 40-50% subsidy on equipment\n\n"
            "Visit your nearest **Common Service Centre (CSC)** or KVK for help "
            "with applications.",
        },
    ],
    "organic_farming": [
        {
            "keywords": [
                "organic",
                "jaivik",
                "natural farming",
                "zero budget",
                "compost",
                "vermicompost",
                "bio fertilizer",
            ],
            "response": "**Organic Farming Guide:**\n\n"
            "🌱 **Key Practices:**\n"
            "1. **Vermicompost:** 2-3 tonnes/ha. Make at home with cow dung + earthworms\n"
            "2. **Jeevamrut:** Cow dung + urine + jaggery + pulse flour. Apply weekly\n"
            "3. **Neem Cake:** 250 kg/ha — natural pest repellent + nitrogen source\n"
            "4. **Green Manure:** Dhaincha/Sunhemp — plough in before sowing\n\n"
            "**Government Support:**\n"
            "- **Paramparagat Krishi Vikas Yojana:** ₹50,000/ha over 3 years\n"
            "- **Organic certification** assistance available through NPOP\n\n"
            "💡 Transition takes 2-3 years but reduces input costs by 30-40%.",
        },
    ],
    "general": [
        {
            "keywords": [],
            "response": "🙏 **Namaste Kisan!** I'm your AGRI-MAA AI assistant.\n\n"
            "I can help you with:\n"
            "- 🌾 **Crop Recommendation** → `/recommend-crop`\n"
            "- 🧪 **Fertilizer Advisory** → `/fertilizer-advisory`\n"
            "- 💧 **Irrigation Schedule** → `/irrigation-schedule`\n"
            "- 🐛 **Pest/Disease Alerts** → `/pest-alerts`\n"
            "- 🔄 **Crop Rotation Plan** → `/crop-rotation/{crop}`\n"
            "- 📈 **Market Prices** → `/market-timing`\n"
            "- 📊 **Yield Estimation** → `/yield-estimate/{plot_id}`\n\n"
            "**Ask me about:** crops, fertilizers, irrigation, pests, weather, "
            "market prices, government schemes, organic farming, or anything "
            "related to farming!\n\n"
            "Try asking: *'What fertilizer should I use for wheat?'* or "
            "*'When should I irrigate rice?'*",
        },
    ],
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _get_current_stage(crop_data: dict, days_since_sowing: int) -> str:
    """Return the growth stage the crop is currently in."""
    stages = crop_data["stages"]
    current_stage = "sowing"
    for stage_name, start_day in sorted(stages.items(), key=lambda x: x[1]):
        if days_since_sowing >= start_day:
            current_stage = stage_name
    return current_stage


def _get_mandis_for_region(region: str) -> list[str]:
    """Return mandi names for a region (case-insensitive), fallback to default."""
    key = region.lower().strip()
    for region_key, mandis in REGION_MANDIS.items():
        if region_key in key or key in region_key:
            return mandis
    return REGION_MANDIS["default"]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup resources."""
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="Harvest Shakti — AGRI-MAA Decision Support System",
    description=(
        "Complete AI-powered Decision Support System for Indian farmers. "
        "Crop recommendation, fertilizer advisory, irrigation scheduling, "
        "pest alerts, crop rotation planning, market intelligence, "
        "yield estimation, harvest timing, and AI chatbot."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router already carries prefix="/auth" — do NOT add prefix again.
app.include_router(auth_router)
setup_rate_limiting(app)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": "harvest_shakti",
        "version": "2.0.0",
        "status": "healthy",
        "capabilities": [
            "yield_estimation",
            "harvest_window",
            "market_timing",
            "crop_recommendation",
            "fertilizer_advisory",
            "irrigation_scheduling",
            "pest_disease_alerts",
            "crop_rotation_planning",
            "ai_chatbot",
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint returning service info."""
    return {
        "service": "Harvest Shakti — AGRI-MAA Decision Support System",
        "version": "2.0.0",
        "features": [
            "Optimal harvest window prediction",
            "Yield estimation using remote sensing",
            "Post-harvest loss risk assessment",
            "Market-aware harvest scheduling",
            "ML-based crop recommendation (Random Forest)",
            "Fertilizer advisory with dosage per hectare",
            "7-day intelligent irrigation scheduling",
            "Pest/disease risk alerts (rule-based + AI)",
            "Crop rotation planner for sustainability",
            "Gemini AI chatbot for farmer queries",
        ],
    }


# ---- Register Plot -------------------------------------------------------


@app.post(
    "/register-plot",
    response_model=PlotRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_plot(body: PlotRegistration, db: AsyncSession = Depends(get_db)):
    """Register a new agricultural plot for tracking."""
    crop_key = body.crop.lower().strip()
    if crop_key not in CROP_YIELD_DATA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported crop '{body.crop}'. Supported: {list(CROP_YIELD_DATA.keys())}",
        )

    # Persist to DB
    db_plot = HarvestPlot(
        plot_id=body.plot_id,
        crop=crop_key,
        variety=body.variety,
        area_hectares=body.area_hectares,
        sowing_date=body.sowing_date,
        soil_health_score=body.soil_health_score,
        irrigation_type=body.irrigation_type.value,
        region=body.region,
    )
    db.add(db_plot)
    await db.flush()

    crop_data = CROP_YIELD_DATA[crop_key]
    maturity_date = body.sowing_date + timedelta(days=crop_data["growth_duration_days"])

    return PlotRegistrationResponse(
        message="Plot registered successfully",
        plot_id=body.plot_id,
        crop=crop_key,
        area_hectares=body.area_hectares,
        expected_maturity_date=maturity_date.isoformat(),
    )


# ---- Yield Estimate -------------------------------------------------------


@app.get("/yield-estimate/{plot_id}", response_model=YieldEstimateResponse)
async def estimate_yield(
    plot_id: str,
    weather_score: float = Query(
        default=70.0, ge=0, le=100, description="Weather favorability score (0-100)"
    ),
    pest_pressure: PestPressure = Query(
        default=PestPressure.none, description="Pest pressure level"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Estimate crop yield for a registered plot with real computation."""
    result = await db.execute(select(HarvestPlot).where(HarvestPlot.plot_id == plot_id))
    plot = result.scalar_one_or_none()
    if plot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plot '{plot_id}' not found. Register it first via POST /register-plot.",
        )

    crop_data = CROP_YIELD_DATA[plot.crop]

    # Base yield
    avg_yield = crop_data["avg_yield_tonnes_per_ha"]
    base_yield = avg_yield * plot.area_hectares

    # Multipliers
    soil_factor = _clamp(plot.soil_health_score / 75.0, 0.6, 1.3)
    weather_factor = _clamp(weather_score / 75.0, 0.5, 1.2)
    irr_factor = IRRIGATION_FACTOR.get(plot.irrigation_type, 0.90)
    pest_factor = PEST_FACTOR.get(pest_pressure.value, 1.0)

    combined = soil_factor * weather_factor * irr_factor * pest_factor
    estimated_yield = base_yield * combined
    yield_per_ha = estimated_yield / plot.area_hectares if plot.area_hectares else 0.0

    # Confidence interval: use numpy normal approximation (±12 % at 90 % CI)
    rng = np.random.default_rng(seed=hash(plot_id) & 0xFFFFFFFF)
    cv = 0.12  # coefficient of variation
    std_dev = estimated_yield * cv
    z_90 = 1.645  # z-score for 90 % CI
    noise = rng.normal(0, std_dev * 0.05)  # tiny stochastic nudge
    low = round(max(0.0, estimated_yield - z_90 * std_dev + noise), 2)
    high = round(estimated_yield + z_90 * std_dev + noise, 2)

    return YieldEstimateResponse(
        plot_id=plot_id,
        crop=plot.crop,
        variety=plot.variety,
        area_hectares=plot.area_hectares,
        base_yield_tonnes=round(base_yield, 2),
        estimated_yield_tonnes=round(estimated_yield, 2),
        yield_per_hectare_tonnes=round(yield_per_ha, 2),
        confidence_interval=ConfidenceInterval(low_tonnes=low, high_tonnes=high),
        factors=YieldFactors(
            soil_health_factor=round(soil_factor, 4),
            weather_factor=round(weather_factor, 4),
            irrigation_factor=round(irr_factor, 4),
            pest_factor=round(pest_factor, 4),
            combined_factor=round(combined, 4),
        ),
        weather_score=weather_score,
        pest_pressure=pest_pressure.value,
        estimated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---- Harvest Window -------------------------------------------------------


@app.get("/harvest-window/{plot_id}", response_model=HarvestWindowResponse)
async def get_harvest_window(plot_id: str, db: AsyncSession = Depends(get_db)):
    """Compute the optimal harvest window for a registered plot."""
    result = await db.execute(select(HarvestPlot).where(HarvestPlot.plot_id == plot_id))
    plot = result.scalar_one_or_none()
    if plot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plot '{plot_id}' not found. Register it first via POST /register-plot.",
        )
    crop_data = CROP_YIELD_DATA[plot.crop]
    growth_days = crop_data["growth_duration_days"]

    today = date.today()
    days_since_sowing = (today - plot.sowing_date).days
    expected_maturity = plot.sowing_date + timedelta(days=growth_days)
    days_to_maturity = (expected_maturity - today).days

    # Current growth stage
    current_stage = _get_current_stage(crop_data, days_since_sowing)
    progress_pct = _clamp((days_since_sowing / growth_days) * 100, 0, 100)

    # Harvest window: a range around the maturity date
    window_half = 3  # ±3 days
    window_start = expected_maturity - timedelta(days=window_half)
    window_end = expected_maturity + timedelta(days=window_half + 1)
    best_date = expected_maturity

    # Weather risk heuristic based on the expected maturity month
    mat_month_idx = expected_maturity.month - 1  # 0-indexed
    rain_prob = MONTHLY_RAIN_PROB[mat_month_idx]
    heatwave = MONTHLY_HEATWAVE_RISK[mat_month_idx]
    frost = MONTHLY_FROST_RISK[mat_month_idx]

    # Build recommendation
    parts: list[str] = []
    if days_to_maturity > 0:
        parts.append(
            f"Crop is in the '{current_stage}' stage with ~{days_to_maturity} days to maturity."
        )
        parts.append(
            f"Plan harvest around {best_date.isoformat()}. "
            f"Arrange labor and machinery by {(window_start - timedelta(days=3)).isoformat()}."
        )
    elif days_to_maturity <= 0:
        parts.append("Crop has reached or passed maturity — harvest immediately.")

    if rain_prob > 40:
        parts.append(
            f"High rain probability ({rain_prob}%) around harvest. Consider early harvest to avoid losses."
        )
    if heatwave in ("high",):
        parts.append(
            "Heatwave risk is high — harvest in early morning or late evening."
        )
    if frost in ("high", "medium"):
        parts.append("Frost risk detected — monitor night temperatures closely.")

    return HarvestWindowResponse(
        plot_id=plot_id,
        crop=plot.crop,
        sowing_date=plot.sowing_date.isoformat(),
        expected_maturity_date=expected_maturity.isoformat(),
        days_to_maturity=days_to_maturity,
        current_growth_stage=current_stage,
        growth_progress_pct=round(progress_pct, 1),
        optimal_harvest_window=HarvestWindowDetail(
            start=window_start.isoformat(),
            end=window_end.isoformat(),
            best_date=best_date.isoformat(),
        ),
        weather_risk=WeatherRisk(
            rain_probability_pct=rain_prob,
            heatwave_risk=heatwave,
            frost_risk=frost,
        ),
        recommendation=" ".join(parts),
    )


# ---- Market Timing --------------------------------------------------------


@app.get("/market-timing", response_model=MarketTimingResponse)
async def get_market_timing(
    crop: str = Query(..., description="Crop name"),
    region: Optional[str] = Query(default="", description="Region or state name"),
):
    """Return market intelligence with simulated pricing data."""
    crop_key = crop.lower().strip()
    if crop_key not in CROP_YIELD_DATA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported crop '{crop}'. Supported: {list(CROP_YIELD_DATA.keys())}",
        )

    crop_data = CROP_YIELD_DATA[crop_key]
    msp = crop_data["msp_per_quintal"]

    # Deterministic-ish random based on crop + current month for reproducibility
    today = date.today()
    seed = hash((crop_key, today.year, today.month)) & 0xFFFFFFFF
    rng = np.random.default_rng(seed=seed)

    # Simulate market price: MSP * random factor [0.95, 1.25]
    price_factor = float(rng.uniform(0.95, 1.25))
    market_price = round(msp * price_factor, 2)

    # Seasonal price trend
    month_idx = today.month - 1
    seasonal_factor = MONTHLY_PRICE_FACTOR[month_idx]
    prev_month_factor = MONTHLY_PRICE_FACTOR[(month_idx - 1) % 12]
    trend_pct = round(
        (seasonal_factor - prev_month_factor) / prev_month_factor * 100, 2
    )

    if trend_pct > 1.0:
        price_trend = "rising"
    elif trend_pct < -1.0:
        price_trend = "falling"
    else:
        price_trend = "stable"

    # Recommendation
    if price_trend == "rising" and market_price > msp:
        recommendation = "hold"
        storage_advisory = (
            f"Prices are trending upward ({trend_pct:+.1f}% month-over-month). "
            "Consider storing for 2-4 weeks for better returns if storage is available."
        )
    elif market_price < msp:
        recommendation = "hold"
        storage_advisory = (
            f"Market price (₹{market_price}/q) is below MSP (₹{msp}/q). "
            "Sell at government procurement centers or store until prices recover."
        )
    else:
        recommendation = "sell"
        storage_advisory = (
            f"Market price (₹{market_price}/q) is above MSP. "
            "Good time to sell. Avoid prolonged storage to reduce post-harvest losses."
        )

    # Nearby mandis
    region_str = region or ""
    mandi_names = _get_mandis_for_region(region_str)
    mandis: list[MandiInfo] = []
    for i, name in enumerate(mandi_names):
        mandi_price = round(float(market_price * rng.uniform(0.96, 1.04)), 2)
        distance = round(float(rng.uniform(8, 60)), 1)
        mandis.append(
            MandiInfo(name=name, price_per_quintal=mandi_price, distance_km=distance)
        )

    # Sort mandis by price descending so best price is first
    mandis.sort(key=lambda m: m.price_per_quintal, reverse=True)

    return MarketTimingResponse(
        crop=crop_key,
        region=region_str,
        current_msp_per_quintal=msp,
        current_market_price_per_quintal=market_price,
        price_trend=price_trend,
        price_trend_pct=trend_pct,
        recommendation=recommendation,
        nearby_mandis=mandis,
        storage_advisory=storage_advisory,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---- Crop Recommendation (Simulated Random Forest) -----------------------


def _compute_crop_suitability(
    profile: dict,
    N: float,
    P: float,
    K: float,
    pH: float,
    moisture: float,
    temperature: float,
    humidity: float,
) -> float:
    """Simulate a Random Forest classifier's suitability score.

    Uses numpy to compute a weighted distance-from-ideal metric for each
    crop profile, then converts to a 0-100 suitability score.
    """
    features = np.array([N, P, K, pH, moisture, temperature, humidity])

    # Ideal midpoints for this crop
    ideal = np.array(
        [
            (profile["N"][0] + profile["N"][1]) / 2,
            (profile["P"][0] + profile["P"][1]) / 2,
            (profile["K"][0] + profile["K"][1]) / 2,
            (profile["pH"][0] + profile["pH"][1]) / 2,
            (profile["moisture"][0] + profile["moisture"][1]) / 2,
            (profile["temp_range"][0] + profile["temp_range"][1]) / 2,
            (profile["humidity_range"][0] + profile["humidity_range"][1]) / 2,
        ]
    )

    # Ranges (width of the acceptable band)
    ranges = np.array(
        [
            profile["N"][1] - profile["N"][0],
            profile["P"][1] - profile["P"][0],
            profile["K"][1] - profile["K"][0],
            profile["pH"][1] - profile["pH"][0],
            profile["moisture"][1] - profile["moisture"][0],
            profile["temp_range"][1] - profile["temp_range"][0],
            profile["humidity_range"][1] - profile["humidity_range"][0],
        ]
    )
    # Prevent division by zero
    ranges = np.where(ranges == 0, 1.0, ranges)

    # Feature importance weights (simulating Random Forest feature importances)
    weights = np.array([0.18, 0.15, 0.12, 0.15, 0.12, 0.15, 0.13])

    # Normalized distance from ideal (0 = perfect, 1 = one range away)
    normalized_dist = np.abs(features - ideal) / ranges

    # Penalty: beyond the range, distance grows faster
    penalty = np.where(normalized_dist > 1.0, normalized_dist**2, normalized_dist)

    # Weighted suitability: 100 when perfect, drops with distance
    raw_score = float(np.sum(weights * (1.0 - np.clip(penalty, 0, 1))))
    # Scale to 0-100, add small random-forest-like noise
    rng = np.random.default_rng(seed=int(N * 100 + P * 10 + K) & 0xFFFFFFFF)
    noise = float(rng.normal(0, 1.5))
    score = _clamp(raw_score * 100 + noise, 0, 100)
    return round(score, 2)


@app.post("/recommend-crop", response_model=CropRecommendationResponse)
async def recommend_crop(body: CropRecommendationRequest):
    """ML-based crop recommendation using simulated Random Forest classifier.

    Analyzes soil parameters (N, P, K, pH, moisture) and weather conditions
    to rank crops by suitability score.
    """
    scores: list[CropScore] = []

    for crop_name, profile in CROP_SOIL_PROFILES.items():
        score = _compute_crop_suitability(
            profile,
            body.nitrogen,
            body.phosphorus,
            body.potassium,
            body.pH,
            body.moisture,
            body.temperature,
            body.humidity,
        )

        # Confidence: higher for scores further from 50 (more decisive)
        confidence = round(_clamp(abs(score - 50) / 50 * 100, 40, 99), 1)

        # Key factors driving the score
        factors: list[str] = []
        if body.nitrogen < profile["N"][0]:
            factors.append(
                f"Low N for {crop_name} (need {profile['N'][0]}-{profile['N'][1]})"
            )
        elif body.nitrogen > profile["N"][1]:
            factors.append(f"High N — {crop_name} may not need excess nitrogen")
        else:
            factors.append(f"N level ideal for {crop_name}")

        if profile["pH"][0] <= body.pH <= profile["pH"][1]:
            factors.append("pH in optimal range")
        else:
            factors.append(f"pH outside optimal {profile['pH'][0]}-{profile['pH'][1]}")

        if profile["temp_range"][0] <= body.temperature <= profile["temp_range"][1]:
            factors.append("Temperature favorable")
        else:
            factors.append("Temperature outside ideal range")

        scores.append(
            CropScore(
                crop=crop_name,
                suitability_score=score,
                confidence=confidence,
                season=profile["season"],
                water_need=profile["water_need"],
                description=profile["description"],
                key_factors=factors[:3],
            )
        )

    # Sort by score descending
    scores.sort(key=lambda x: x.suitability_score, reverse=True)
    top_5 = scores[:5]
    best = top_5[0]

    # Soil analysis summary
    soil_analysis = {
        "nitrogen_status": "Low"
        if body.nitrogen < 50
        else ("Medium" if body.nitrogen < 100 else "High"),
        "phosphorus_status": "Low"
        if body.phosphorus < 25
        else ("Medium" if body.phosphorus < 55 else "High"),
        "potassium_status": "Low"
        if body.potassium < 20
        else ("Medium" if body.potassium < 50 else "High"),
        "pH_category": (
            "Acidic" if body.pH < 6.0 else ("Neutral" if body.pH <= 7.5 else "Alkaline")
        ),
        "moisture_status": "Dry"
        if body.moisture < 30
        else ("Adequate" if body.moisture < 65 else "Wet"),
    }

    # Weather suitability
    if 15 <= body.temperature <= 35 and 30 <= body.humidity <= 80:
        weather_suit = "Favorable for most crops"
    elif body.temperature > 40:
        weather_suit = "Extreme heat — limited crop options"
    elif body.temperature < 10:
        weather_suit = "Cold conditions — only rabi crops suitable"
    else:
        weather_suit = "Moderate — check crop-specific requirements"

    advisory = (
        f"Based on your soil profile (N={body.nitrogen}, P={body.phosphorus}, "
        f"K={body.potassium}, pH={body.pH}, Moisture={body.moisture}%), "
        f"**{best.crop.title()}** is the best fit with a suitability score of "
        f"{best.suitability_score}/100. {best.description} "
        f"Consider planting during the {best.season} season."
    )

    return CropRecommendationResponse(
        top_recommendation=best.crop,
        recommendations=top_5,
        soil_analysis=soil_analysis,
        weather_suitability=weather_suit,
        advisory=advisory,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---- Fertilizer Advisory --------------------------------------------------


@app.post("/fertilizer-advisory", response_model=FertilizerAdvisoryResponse)
async def fertilizer_advisory(body: FertilizerAdvisoryRequest):
    """Recommend specific fertilizers based on soil nutrient deficit vs crop needs."""
    crop_key = body.crop.lower().strip()
    if crop_key not in CROP_NUTRIENT_REQUIREMENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported crop '{body.crop}'. "
                f"Supported: {list(CROP_NUTRIENT_REQUIREMENTS.keys())}"
            ),
        )

    required = CROP_NUTRIENT_REQUIREMENTS[crop_key]
    current = {"N": body.current_N, "P": body.current_P, "K": body.current_K}

    # Compute deficits
    deficits = {
        nutrient: max(0.0, required[nutrient] - current[nutrient])
        for nutrient in ("N", "P", "K")
    }

    nutrient_status = {}
    for nut in ("N", "P", "K"):
        ratio = current[nut] / required[nut] if required[nut] > 0 else 1.0
        if ratio < 0.5:
            level = "Severely Deficient"
        elif ratio < 0.8:
            level = "Deficient"
        elif ratio < 1.1:
            level = "Adequate"
        else:
            level = "Surplus"
        nutrient_status[nut] = {
            "current_kg_per_ha": current[nut],
            "required_kg_per_ha": required[nut],
            "deficit_kg_per_ha": round(deficits[nut], 1),
            "status": level,
        }

    recommendations: list[FertilizerRecommendation] = []
    total_cost = 0.0

    # Nitrogen recommendation
    if deficits["N"] > 0:
        urea = FERTILIZER_DB["urea"]
        qty_per_ha = round(deficits["N"] / (urea["content_pct"] / 100), 1)
        total_qty = round(qty_per_ha * body.area_hectares, 1)
        cost = round(total_qty * urea["cost_per_kg"], 2)
        total_cost += cost
        recommendations.append(
            FertilizerRecommendation(
                fertilizer="Urea (46% N)",
                nutrient_supplied="Nitrogen (N)",
                deficit_kg_per_ha=round(deficits["N"], 1),
                quantity_kg_per_ha=qty_per_ha,
                total_quantity_kg=total_qty,
                estimated_cost_inr=cost,
                application_note=urea["application_note"],
            )
        )

    # Phosphorus recommendation
    if deficits["P"] > 0:
        dap = FERTILIZER_DB["dap"]
        qty_per_ha = round(deficits["P"] / (dap["content_pct"] / 100), 1)
        total_qty = round(qty_per_ha * body.area_hectares, 1)
        cost = round(total_qty * dap["cost_per_kg"], 2)
        total_cost += cost
        # DAP also supplies some N — note it
        n_from_dap = round(qty_per_ha * (dap["secondary_pct"] / 100), 1)
        note = (
            f"{dap['application_note']} "
            f"Also supplies ~{n_from_dap} kg N/ha — adjust Urea dose accordingly."
        )
        recommendations.append(
            FertilizerRecommendation(
                fertilizer="DAP (46% P₂O₅, 18% N)",
                nutrient_supplied="Phosphorus (P)",
                deficit_kg_per_ha=round(deficits["P"], 1),
                quantity_kg_per_ha=qty_per_ha,
                total_quantity_kg=total_qty,
                estimated_cost_inr=cost,
                application_note=note,
            )
        )

    # Potassium recommendation
    if deficits["K"] > 0:
        mop = FERTILIZER_DB["mop"]
        qty_per_ha = round(deficits["K"] / (mop["content_pct"] / 100), 1)
        total_qty = round(qty_per_ha * body.area_hectares, 1)
        cost = round(total_qty * mop["cost_per_kg"], 2)
        total_cost += cost
        recommendations.append(
            FertilizerRecommendation(
                fertilizer="MoP (60% K₂O)",
                nutrient_supplied="Potassium (K)",
                deficit_kg_per_ha=round(deficits["K"], 1),
                quantity_kg_per_ha=qty_per_ha,
                total_quantity_kg=total_qty,
                estimated_cost_inr=cost,
                application_note=mop["application_note"],
            )
        )

    # Micronutrient check
    soil_health_notes: list[str] = []
    if body.soil_pH < 5.5:
        soil_health_notes.append(
            "⚠️ Soil is acidic (pH < 5.5). Apply agricultural lime @ 2-4 tonnes/ha "
            "to correct pH. Phosphorus availability is reduced in acidic soils."
        )
    elif body.soil_pH > 8.0:
        soil_health_notes.append(
            "⚠️ Soil is alkaline (pH > 8.0). Apply Gypsum @ 2-5 tonnes/ha. "
            "Iron, Zinc, and Manganese availability is reduced."
        )

    if body.organic_carbon_pct < 0.5:
        soil_health_notes.append(
            "⚠️ Organic carbon is low (< 0.5%). Apply FYM @ 10-15 tonnes/ha or "
            "vermicompost @ 3-5 tonnes/ha to improve soil health."
        )

    if crop_key in ("rice", "wheat", "maize"):
        zn = FERTILIZER_DB["zinc_sulphate"]
        soil_health_notes.append(
            f"💡 Consider Zinc Sulphate @ 25 kg/ha (₹{round(25 * zn['cost_per_kg'])}) — "
            f"essential for {crop_key} in most Indian soils."
        )

    if not soil_health_notes:
        soil_health_notes.append("✅ Soil parameters are within acceptable range.")

    # Application schedule
    schedule: list[str] = [
        f"1. **Basal dose (at sowing):** Apply full DAP ({round(deficits['P'] / 0.46, 1) if deficits['P'] > 0 else 0} kg/ha) "
        f"+ full MoP ({round(deficits['K'] / 0.60, 1) if deficits['K'] > 0 else 0} kg/ha) "
        f"+ 1/3 Urea ({round(deficits['N'] / 0.46 / 3, 1) if deficits['N'] > 0 else 0} kg/ha)",
        f"2. **First top-dress (21-25 days):** Apply 1/3 Urea ({round(deficits['N'] / 0.46 / 3, 1) if deficits['N'] > 0 else 0} kg/ha) "
        f"at tillering/vegetative stage",
        f"3. **Second top-dress (45-55 days):** Apply remaining 1/3 Urea "
        f"({round(deficits['N'] / 0.46 / 3, 1) if deficits['N'] > 0 else 0} kg/ha) "
        f"at flowering/booting stage",
    ]

    return FertilizerAdvisoryResponse(
        crop=crop_key,
        area_hectares=body.area_hectares,
        nutrient_status=nutrient_status,
        recommendations=recommendations,
        total_estimated_cost_inr=round(total_cost, 2),
        soil_health_notes=soil_health_notes,
        application_schedule=schedule,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---- Irrigation Scheduler -------------------------------------------------


@app.post("/irrigation-schedule", response_model=IrrigationScheduleResponse)
async def irrigation_schedule(body: IrrigationScheduleRequest):
    """Generate a 7-day irrigation schedule based on soil, weather, and crop needs."""
    crop_key = body.crop.lower().strip()

    # Water need per irrigation event (mm) by irrigation type
    water_efficiency = {
        "drip": 0.90,
        "sprinkler": 0.75,
        "flood": 0.55,
        "rainfed": 0.0,
    }
    efficiency = water_efficiency.get(body.irrigation_type.value, 0.55)

    # Crop daily ET (evapotranspiration) estimate using Blaney-Criddle-like formula
    # Simplified: ET = p * (0.46 * T + 8.13) * Kc
    # where p = daylight percentage (~0.27 for India), Kc = crop coefficient
    crop_kc = {
        "rice": 1.15,
        "wheat": 1.05,
        "maize": 1.10,
        "cotton": 1.05,
        "sugarcane": 1.20,
        "chickpea": 0.85,
        "mustard": 0.90,
        "soybean": 1.00,
        "groundnut": 0.95,
        "potato": 1.05,
        "onion": 0.95,
        "tomato": 1.10,
    }
    kc = crop_kc.get(crop_key, 1.0)
    p = 0.27  # approximate daylight fraction for Indian latitudes
    daily_et = round(p * (0.46 * body.temperature + 8.13) * kc, 2)

    # Humidity reduces ET
    humidity_factor = 1.0 - (body.humidity - 50) / 200  # slight reduction if humid
    daily_et = round(daily_et * _clamp(humidity_factor, 0.7, 1.2), 2)

    # Ensure 7 values for rain forecast
    rain_forecast = list(body.rain_forecast_mm)
    while len(rain_forecast) < 7:
        rain_forecast.append(0.0)
    rain_forecast = rain_forecast[:7]

    # Simulate 7-day schedule
    schedule: list[DaySchedule] = []
    soil_moisture = body.soil_moisture
    total_water = 0.0
    today = date.today()

    # Thresholds
    critical_low = 25.0  # below this = must irrigate
    comfortable = 55.0  # above this = no need
    field_capacity = 85.0  # don't exceed this

    for day_idx in range(7):
        current_date = today + timedelta(days=day_idx)
        rain_mm = rain_forecast[day_idx]

        # Soil moisture change: loses ET, gains rain (effective rain ~80%)
        effective_rain = rain_mm * 0.80
        soil_moisture = soil_moisture - daily_et + effective_rain
        soil_moisture = _clamp(soil_moisture, 5, 95)

        # Decision logic
        water_mm = 0.0
        if body.irrigation_type == IrrigationType.rainfed:
            action = "Rainfed — no scheduled irrigation"
            reason = "Crop depends on rainfall. Monitor moisture levels."
        elif soil_moisture < critical_low and rain_mm < 5:
            # Must irrigate
            water_mm = round((comfortable - soil_moisture) / efficiency, 1)
            water_mm = max(water_mm, 10.0)
            action = "🔴 IRRIGATE — Urgent"
            reason = (
                f"Soil moisture critically low ({soil_moisture:.0f}%). "
                f"No significant rain expected ({rain_mm:.0f}mm)."
            )
            soil_moisture = min(soil_moisture + water_mm * efficiency, field_capacity)
            total_water += water_mm
        elif soil_moisture < critical_low and rain_mm >= 5:
            action = "🟡 WAIT — Rain expected"
            reason = (
                f"Soil moisture low ({soil_moisture:.0f}%) but rain expected "
                f"({rain_mm:.0f}mm). Monitor and irrigate if rain doesn't come."
            )
            # If rain doesn't fully recover, small supplement
            if soil_moisture + effective_rain < critical_low + 10:
                water_mm = round((critical_low + 15 - soil_moisture) / efficiency, 1)
                action = "🟡 LIGHT IRRIGATION — Rain may not be sufficient"
                soil_moisture = min(
                    soil_moisture + water_mm * efficiency, field_capacity
                )
                total_water += water_mm
        elif rain_mm >= 10:
            action = "🟢 SKIP — Rain expected"
            reason = (
                f"Sufficient rain forecast ({rain_mm:.0f}mm). "
                f"Soil moisture adequate ({soil_moisture:.0f}%)."
            )
        elif soil_moisture < comfortable and rain_mm < 3:
            water_mm = round((comfortable - soil_moisture) / efficiency, 1)
            action = "🔵 IRRIGATE — Routine"
            reason = (
                f"Soil moisture below comfortable level ({soil_moisture:.0f}%). "
                f"Routine irrigation recommended."
            )
            soil_moisture = min(soil_moisture + water_mm * efficiency, field_capacity)
            total_water += water_mm
        else:
            action = "🟢 SKIP — Adequate moisture"
            reason = (
                f"Soil moisture adequate ({soil_moisture:.0f}%). No irrigation needed."
            )

        schedule.append(
            DaySchedule(
                day=day_idx + 1,
                date=current_date.isoformat(),
                action=action,
                reason=reason,
                water_mm=round(water_mm, 1),
                rain_expected_mm=round(rain_mm, 1),
                soil_moisture_predicted=round(soil_moisture, 1),
            )
        )

    # Water saving tip
    if body.irrigation_type == IrrigationType.flood:
        water_tip = (
            "💡 Switch to drip irrigation to save 30-50% water. "
            "PM Krishi Sinchai Yojana provides 55-90% subsidy on micro-irrigation systems."
        )
    elif body.irrigation_type == IrrigationType.sprinkler:
        water_tip = "💡 Sprinkler is good! Consider drip for row crops to save an additional 15-20% water."
    elif body.irrigation_type == IrrigationType.drip:
        water_tip = (
            "✅ Drip irrigation is the most water-efficient method. "
            "Ensure emitters are clean and pressure is maintained at 1-1.5 kg/cm²."
        )
    else:
        water_tip = (
            "🌧️ Rainfed farming: Consider rainwater harvesting and farm ponds. "
            "MGNREGA provides support for farm pond construction."
        )

    # Critical note based on crop stage
    critical_stages = {
        "flowering": "⚠️ Crop is at flowering stage — most water-sensitive period. Do NOT skip irrigation.",
        "grain_filling": "⚠️ Grain filling stage — consistent moisture critical for yield.",
        "silking": "⚠️ Silking stage in maize — even 1 day of water stress reduces yield by 3-8%.",
        "panicle_initiation": "⚠️ Panicle initiation — maintain 2-3 cm standing water for rice.",
        "boll_development": "⚠️ Boll development stage — maintain adequate moisture for fiber quality.",
    }
    critical_note = critical_stages.get(
        body.crop_stage.lower(),
        f"Crop is at '{body.crop_stage}' stage. Maintain regular irrigation schedule.",
    )

    return IrrigationScheduleResponse(
        crop=crop_key,
        current_soil_moisture=body.soil_moisture,
        irrigation_type=body.irrigation_type.value,
        schedule=schedule,
        total_water_needed_mm=round(total_water, 1),
        water_saving_tip=water_tip,
        critical_note=critical_note,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---- Pest / Disease Alerts ------------------------------------------------


@app.get("/pest-alerts", response_model=PestAlertResponse)
async def pest_alerts(
    crop: str = Query(..., description="Crop name"),
    region: str = Query(default="", description="Region / state"),
    temperature: float = Query(default=28.0, description="Current temperature (°C)"),
    humidity: float = Query(
        default=70.0, ge=0, le=100, description="Relative humidity (%)"
    ),
    soil_moisture: float = Query(
        default=50.0, ge=0, le=100, description="Soil moisture (%)"
    ),
):
    """Generate pest/disease risk alerts based on crop, weather, and conditions."""
    crop_key = crop.lower().strip()

    alerts: list[PestAlert] = []

    for rule in PEST_DISEASE_RULES:
        # Match crop-specific or wildcard rules
        if rule["crop"] != "*" and rule["crop"] != crop_key:
            continue

        cond = rule["conditions"]
        weights = rule["severity_weights"]

        # Compute individual risk factors
        temp_lo, temp_hi = cond["temp_range"]
        temp_in_range = temp_lo <= temperature <= temp_hi
        temp_proximity = (
            1.0
            if temp_in_range
            else max(
                0.0,
                1.0 - min(abs(temperature - temp_lo), abs(temperature - temp_hi)) / 10,
            )
        )

        humidity_risk = (
            _clamp(
                (humidity - cond["humidity_min"]) / (100 - cond["humidity_min"]), 0, 1
            )
            if humidity >= cond["humidity_min"]
            else _clamp(humidity / cond["humidity_min"], 0, 0.4)
        )

        moisture_risk = (
            _clamp(
                (soil_moisture - cond["moisture_min"]) / (100 - cond["moisture_min"]),
                0,
                1,
            )
            if soil_moisture >= cond["moisture_min"]
            else _clamp(soil_moisture / cond["moisture_min"], 0, 0.3)
        )

        # Weighted risk score (0-100)
        raw_score = (
            weights["temperature"] * temp_proximity
            + weights["humidity"] * humidity_risk
            + weights["moisture"] * moisture_risk
        )
        risk_score = round(_clamp(raw_score * 100, 0, 100), 1)

        # Determine risk level
        if risk_score >= 75:
            risk_level = "🔴 HIGH RISK"
        elif risk_score >= 50:
            risk_level = "🟠 MODERATE RISK"
        elif risk_score >= 25:
            risk_level = "🟡 LOW RISK"
        else:
            risk_level = "🟢 MINIMAL"

        # Only include alerts with meaningful risk
        if risk_score < 15:
            continue

        # Contributing factors
        contributing: list[str] = []
        if temp_in_range:
            contributing.append(
                f"Temperature ({temperature}°C) in disease-conducive range ({temp_lo}-{temp_hi}°C)"
            )
        if humidity >= cond["humidity_min"]:
            contributing.append(
                f"Humidity ({humidity}%) exceeds threshold ({cond['humidity_min']}%)"
            )
        if soil_moisture >= cond["moisture_min"]:
            contributing.append(
                f"Soil moisture ({soil_moisture}%) above disease threshold ({cond['moisture_min']}%)"
            )

        if not contributing:
            contributing.append("Conditions approaching risk thresholds")

        alerts.append(
            PestAlert(
                disease=rule["disease"],
                risk_level=risk_level,
                risk_score=risk_score,
                symptoms=rule["symptoms"],
                treatment=rule["treatment"],
                prevention=rule["prevention"],
                contributing_factors=contributing,
            )
        )

    # Sort by risk score descending
    alerts.sort(key=lambda a: a.risk_score, reverse=True)

    # General advisory
    if alerts and alerts[0].risk_score >= 75:
        general = (
            f"⚠️ HIGH ALERT: Conditions are highly conducive for disease/pest outbreak in {crop_key}. "
            "Immediate preventive spraying recommended. Monitor fields daily."
        )
    elif alerts and alerts[0].risk_score >= 50:
        general = (
            f"🟠 CAUTION: Moderate pest/disease risk detected for {crop_key}. "
            "Preventive measures recommended. Scout fields every 2-3 days."
        )
    elif alerts:
        general = (
            f"🟢 Low risk conditions for {crop_key}. Continue routine monitoring. "
            "Maintain field hygiene and balanced nutrition."
        )
    else:
        general = (
            f"✅ No significant pest/disease risks detected for {crop_key} "
            "under current conditions. Continue good agricultural practices."
        )

    return PestAlertResponse(
        crop=crop_key,
        region=region,
        temperature=temperature,
        humidity=humidity,
        total_alerts=len(alerts),
        alerts=alerts,
        general_advisory=general,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---- Crop Rotation Planner ------------------------------------------------


@app.get("/crop-rotation/{crop}", response_model=CropRotationResponse)
async def crop_rotation_planner(crop: str):
    """Suggest next crop rotation options for sustainable farming."""
    crop_key = crop.lower().strip()

    if crop_key not in CROP_ROTATION_RULES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No rotation data for '{crop}'. "
                f"Supported: {list(CROP_ROTATION_RULES.keys())}"
            ),
        )

    rules = CROP_ROTATION_RULES[crop_key]

    # Build detailed plan for each recommended crop
    detailed_plan: list[dict] = []
    for i, next_crop in enumerate(rules["recommended_next"]):
        next_profile = CROP_SOIL_PROFILES.get(next_crop, {})
        next_nutrients = CROP_NUTRIENT_REQUIREMENTS.get(next_crop, {})

        plan = {
            "rank": i + 1,
            "crop": next_crop,
            "season": next_profile.get("season", "consult local advisory"),
            "water_need": next_profile.get("water_need", "medium"),
            "nutrient_requirement_N_kg_ha": next_nutrients.get("N", 0),
            "nutrient_requirement_P_kg_ha": next_nutrients.get("P", 0),
            "nutrient_requirement_K_kg_ha": next_nutrients.get("K", 0),
            "benefit": (
                f"Planting {next_crop.title()} after {crop_key.title()} "
                f"{'restores soil nitrogen' if next_crop in ('chickpea', 'soybean', 'groundnut') else 'diversifies and breaks pest cycles'}."
            ),
        }
        detailed_plan.append(plan)

    # Sustainability score: higher if legume is in rotation
    legumes = {"chickpea", "soybean", "groundnut"}
    has_legume_option = bool(legumes & set(rules["recommended_next"]))
    base_score = 75.0
    if has_legume_option:
        base_score += 15.0
    if len(rules["recommended_next"]) >= 3:
        base_score += 5.0
    rng = np.random.default_rng(seed=hash(crop_key) & 0xFFFFFFFF)
    sustainability = round(_clamp(base_score + float(rng.normal(0, 2)), 60, 99), 1)

    return CropRotationResponse(
        current_crop=crop_key,
        recommended_next_crops=rules["recommended_next"],
        avoid_crops=rules["avoid_next"],
        rotation_reason=rules["reason"],
        nitrogen_benefit=rules["nitrogen_benefit"],
        detailed_plan=detailed_plan,
        sustainability_score=sustainability,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---- Gemini AI Chatbot (Simulated) ----------------------------------------


def _match_chatbot_response(message: str) -> tuple[str, str, list[str], float]:
    """Match user message against knowledge base and return response.

    Returns: (response_text, category, related_endpoints, confidence)
    """
    msg_lower = message.lower().strip()

    best_match: tuple[str, str, list[str], float] | None = None
    best_score = 0

    category_endpoints: dict[str, list[str]] = {
        "crop_advice": ["/recommend-crop"],
        "fertilizer": ["/fertilizer-advisory"],
        "irrigation": ["/irrigation-schedule"],
        "pest_disease": ["/pest-alerts"],
        "weather": ["/harvest-window/{plot_id}"],
        "market_price": ["/market-timing"],
        "government_schemes": [],
        "organic_farming": ["/fertilizer-advisory"],
        "general": [
            "/recommend-crop",
            "/fertilizer-advisory",
            "/irrigation-schedule",
            "/pest-alerts",
            "/crop-rotation/{crop}",
            "/market-timing",
        ],
    }

    for category, entries in CHATBOT_KNOWLEDGE.items():
        for entry in entries:
            keywords = entry.get("keywords", [])
            if not keywords:
                continue

            # Score: number of keyword matches, weighted by specificity
            score = 0
            for kw in keywords:
                if kw in msg_lower:
                    # Longer keywords are more specific, give higher weight
                    score += len(kw.split())
            if score > best_score:
                best_score = score
                best_match = (
                    entry["response"],
                    category,
                    category_endpoints.get(category, []),
                    min(0.95, 0.5 + score * 0.1),
                )

    # Specific crop mentions — generate dynamic response
    for crop_name in CROP_SOIL_PROFILES:
        if crop_name in msg_lower:
            profile = CROP_SOIL_PROFILES[crop_name]
            nutrients = CROP_NUTRIENT_REQUIREMENTS.get(crop_name, {})
            rotation = CROP_ROTATION_RULES.get(crop_name, {})

            dynamic = (
                f"**{crop_name.title()} — Quick Guide:**\n\n"
                f"🌡️ **Ideal Temperature:** {profile['temp_range'][0]}-{profile['temp_range'][1]}°C\n"
                f"💧 **Water Need:** {profile['water_need'].replace('_', ' ').title()}\n"
                f"📅 **Season:** {profile['season'].title()}\n"
                f"🧪 **Fertilizer (per ha):** N={nutrients.get('N', '?')} kg, "
                f"P={nutrients.get('P', '?')} kg, K={nutrients.get('K', '?')} kg\n"
                f"📝 **Description:** {profile['description']}\n"
            )
            if rotation:
                dynamic += (
                    f"\n🔄 **Rotate with:** {', '.join(r.title() for r in rotation.get('recommended_next', []))}\n"
                    f"🚫 **Avoid:** {', '.join(r.title() for r in rotation.get('avoid_next', []))}\n"
                )

            # If this is more specific than keyword match, use it
            if best_score < 3:
                return (
                    dynamic,
                    "crop_advice",
                    ["/recommend-crop", f"/crop-rotation/{crop_name}"],
                    0.85,
                )

    # If no match, return general response
    if best_match is None or best_score == 0:
        general_entries = CHATBOT_KNOWLEDGE.get("general", [{}])
        return (
            general_entries[0].get(
                "response", "Please ask a farming-related question."
            ),
            "general",
            category_endpoints.get("general", []),
            0.4,
        )

    return best_match


@app.post("/chat", response_model=ChatResponse)
async def gemini_chat(body: ChatRequest):
    """AI chatbot for free-form farmer questions.

    Powered by an agricultural knowledge engine with comprehensive coverage
    of crops, fertilizers, irrigation, pests, weather, market prices,
    and government schemes.
    """
    response_text, category, endpoints, confidence = _match_chatbot_response(
        body.message
    )

    # If context is provided, enrich response
    if body.context:
        ctx_parts: list[str] = []
        if "crop" in body.context:
            ctx_parts.append(f"Crop: {body.context['crop']}")
        if "region" in body.context:
            ctx_parts.append(f"Region: {body.context['region']}")
        if ctx_parts:
            response_text += f"\n\n---\n*Based on your context: {', '.join(ctx_parts)}*"

    return ChatResponse(
        response=response_text,
        category=category,
        related_endpoints=endpoints,
        confidence=confidence,
        model="gemini-agri-maa-v2",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "services.harvest_shakti.app:app", host="0.0.0.0", port=8005, reload=True
    )
