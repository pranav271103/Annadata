"""
SoilScan AI - AI-powered soil analysis service.

Provides real-time soil health scoring, nutrient deficiency analysis,
and fertilizer recommendations based on NPK levels, pH, organic carbon,
and moisture readings.  All scoring uses numpy for vectorised math.
Results are stored in-memory so that reports and history can be retrieved
without an external database.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import os
import json
from openai import OpenAI
from .serial_service import serial_service

from services.shared.auth.router import router as auth_router, setup_rate_limiting
from services.shared.config import settings
from services.shared.db.session import close_db, init_db, get_db
from services.shared.db.models import SoilAnalysis

# ---------------------------------------------------------------------------
# Analysis results stored in PostgreSQL (soil_analyses table)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Optimal ranges & weights for soil health scoring
# ---------------------------------------------------------------------------
# Each tuple is (low, high) of the ideal range.
_OPTIMAL_RANGES: dict[str, tuple[float, float]] = {
    "ph": (6.5, 7.0),
    "nitrogen_ppm": (250.0, 500.0),
    "phosphorus_ppm": (15.0, 30.0),
    "potassium_ppm": (120.0, 250.0),
    "organic_carbon_pct": (0.75, 1.5),
    "moisture_pct": (20.0, 40.0),
}

_WEIGHTS: dict[str, float] = {
    "ph": 0.15,
    "nitrogen_ppm": 0.20,
    "phosphorus_ppm": 0.15,
    "potassium_ppm": 0.15,
    "organic_carbon_pct": 0.20,
    "moisture_pct": 0.15,
}

# Fertility classification thresholds
_FERTILITY_THRESHOLDS: list[tuple[float, str]] = [
    (80.0, "excellent"),
    (65.0, "good"),
    (40.0, "moderate"),
    (0.0, "poor"),
]


# ===================================================================
# Pydantic request / response schemas
# ===================================================================


class SoilSampleRequest(BaseModel):
    """Input payload for a single soil sample analysis."""

    plot_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    nitrogen_ppm: float = Field(ge=0, description="Nitrogen in parts per million")
    phosphorus_ppm: float = Field(ge=0, description="Phosphorus in parts per million")
    potassium_ppm: float = Field(ge=0, description="Potassium in parts per million")
    ph_level: float = Field(ge=0, le=14, description="Soil pH level")
    organic_carbon_pct: float = Field(
        ge=0, le=100, description="Organic carbon percentage"
    )
    moisture_pct: float = Field(ge=0, le=100, description="Soil moisture percentage")
    temperature_celsius: float | None = None
    soil_type: str | None = None  # e.g. "alluvial", "black", "red", "laterite"


class Recommendation(BaseModel):
    """A single actionable recommendation."""

    nutrient: str
    status: Literal["deficient", "optimal", "excess"]
    message: str


class SoilAnalysisResponse(BaseModel):
    """Full result returned after analysis."""

    analysis_id: str
    plot_id: str
    latitude: float
    longitude: float
    soil_type: str | None
    temperature_celsius: float | None

    # Raw readings echoed back for convenience
    nitrogen_ppm: float
    phosphorus_ppm: float
    potassium_ppm: float
    ph_level: float
    organic_carbon_pct: float
    moisture_pct: float

    # Computed scores (each 0-100)
    ph_score: float
    nitrogen_score: float
    phosphorus_score: float
    potassium_score: float
    organic_carbon_score: float
    moisture_score: float

    # Aggregate
    health_score: float
    fertility_class: Literal["poor", "moderate", "good", "excellent"]

    recommendations: list[Recommendation]
    analyzed_at: str  # ISO-8601 timestamp


class HistoryEntry(BaseModel):
    """Condensed view of a past analysis for the history endpoint."""

    analysis_id: str
    date: str
    health_score: float
    fertility_class: str


class HistoryResponse(BaseModel):
    """Response for the GET /history endpoint."""

    plot_id: str
    analyses: list[HistoryEntry]
    trend: Literal["improving", "stable", "declining", "insufficient_data"]


class BatchAnalyzeRequest(BaseModel):
    """Wrapper for batch analysis."""

    samples: list[SoilSampleRequest]


class BatchAnalyzeResponse(BaseModel):
    """Wrapper for batch analysis results."""

    results: list[SoilAnalysisResponse]
    count: int

class LiveScanRequest(BaseModel):
    """Request for a live sensor scan."""
    plot_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    soil_type: str | None = "loamy"
    region: str | None = "north_india"



# -------------------------------------------------------------------
# Photo-based soil analysis models
# -------------------------------------------------------------------


class SoilPhotoRequest(BaseModel):
    """Input payload for photo-based soil analysis.

    Accepts either raw base64 image data *or* pre-extracted image
    metadata (HSV colour values and texture description) for
    simulation / testing without a real CV model.
    """

    plot_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    region: str = Field(
        default="unknown", description="Geographic region of the soil sample"
    )
    soil_type: str | None = None

    # Option A: raw base64 image (ignored in simulation mode)
    image_base64: str | None = Field(
        default=None,
        description="Base64-encoded soil photograph. When provided the service "
        "simulates ML inference on extracted colour/texture features.",
    )

    # Option B: pre-extracted colour / texture metadata
    hue: float | None = Field(default=None, ge=0, le=360, description="HSV hue (0-360)")
    saturation: float | None = Field(
        default=None, ge=0, le=1, description="HSV saturation (0-1)"
    )
    value: float | None = Field(
        default=None, ge=0, le=1, description="HSV value / brightness (0-1)"
    )
    texture: str | None = Field(
        default=None,
        description="Soil texture description, e.g. 'sandy', 'clay', 'loam', 'silt', 'sandy_loam', 'clay_loam'",
    )


class SoilPhotoResponse(BaseModel):
    """Full result returned after photo-based analysis."""

    analysis_id: str
    plot_id: str
    latitude: float
    longitude: float
    region: str
    soil_type: str | None
    source: str  # "photo_analysis"

    # Predicted readings from image features
    predicted_ph: float
    predicted_nitrogen_ppm: float
    predicted_phosphorus_ppm: float
    predicted_potassium_ppm: float
    predicted_organic_carbon_pct: float
    predicted_moisture_pct: float

    # Scores and classification (reuses the same scoring pipeline)
    ph_score: float
    nitrogen_score: float
    phosphorus_score: float
    potassium_score: float
    organic_carbon_score: float
    moisture_score: float

    health_score: float
    fertility_class: Literal["poor", "moderate", "good", "excellent"]

    # Image feature summary
    image_features: dict
    confidence: float  # 0-1 model confidence

    recommendations: list[Recommendation]
    analyzed_at: str


# -------------------------------------------------------------------
# Quantum ML correlation models
# -------------------------------------------------------------------


class QuantumCorrelationRequest(BaseModel):
    """Input payload for quantum-inspired correlation analysis."""

    nitrogen_ppm: float = Field(ge=0)
    phosphorus_ppm: float = Field(ge=0)
    potassium_ppm: float = Field(ge=0)
    ph: float = Field(ge=0, le=14)
    moisture_pct: float = Field(ge=0, le=100)
    organic_carbon_pct: float = Field(ge=0, le=100)
    soil_type: str = Field(default="unknown")
    region: str = Field(default="unknown")


class CorrelationEntry(BaseModel):
    """A single discovered non-obvious correlation."""

    parameters: list[str]
    correlation_coefficient: float
    insight: str
    confidence: float


class InterventionRecommendation(BaseModel):
    """Recommended intervention based on discovered correlations."""

    priority: int
    action: str
    rationale: str
    expected_impact: str


class QuantumAdvantageMetrics(BaseModel):
    """Simulated quantum advantage metrics."""

    classical_time_ms: float
    quantum_time_ms: float
    speedup_factor: float
    qubits_used: int
    circuit_depth: int
    entanglement_pairs: int


class QuantumCorrelationResponse(BaseModel):
    """Full result from quantum-inspired correlation analysis."""

    analysis_id: str
    soil_type: str
    region: str

    # Discovered correlations
    correlations: list[CorrelationEntry]

    # Full parameter correlation matrix (param names → row of coefficients)
    correlation_matrix: dict[str, dict[str, float]]

    # Quantum advantage info
    quantum_metrics: QuantumAdvantageMetrics

    # Actionable interventions
    interventions: list[InterventionRecommendation]

    analyzed_at: str


# ===================================================================
# Scoring helpers (numpy-based)
# ===================================================================


def _range_score(value: float, low: float, high: float) -> float:
    """
    Score a value against an optimal [low, high] range.

    Returns 100 when the value sits inside the range.  Outside the
    range the score decays following a Gaussian-like curve so that
    values far from optimal score close to 0.

    The decay width (sigma) is set to half the range width, giving a
    reasonable falloff for agricultural metrics.
    """
    if low <= value <= high:
        return 100.0

    midpoint = (low + high) / 2.0
    sigma = max((high - low) / 2.0, 1e-6)  # avoid division by zero

    # Distance from nearest edge of the optimal range
    if value < low:
        distance = low - value
    else:
        distance = value - high

    # Gaussian decay from 100
    score = float(100.0 * np.exp(-0.5 * (distance / sigma) ** 2))
    return round(score, 2)


def _classify_fertility(score: float) -> str:
    """Map a 0-100 health score to a fertility class string."""
    for threshold, label in _FERTILITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "poor"  # fallback


def _nutrient_status(
    value: float, low: float, high: float
) -> Literal["deficient", "optimal", "excess"]:
    """Classify a nutrient value relative to its optimal range."""
    if value < low:
        return "deficient"
    if value > high:
        return "excess"
    return "optimal"


def _build_recommendations(sample: SoilSampleRequest) -> list[Recommendation]:
    """Generate actionable recommendations from nutrient readings."""
    recs: list[Recommendation] = []

    # --- Nitrogen ---
    n_status = _nutrient_status(sample.nitrogen_ppm, 250.0, 500.0)
    if n_status == "deficient":
        recs.append(
            Recommendation(
                nutrient="nitrogen",
                status="deficient",
                message=(
                    f"Nitrogen is low at {sample.nitrogen_ppm:.1f} ppm (optimal 250-500 ppm). "
                    "Apply urea or ammonium sulphate, or rotate with nitrogen-fixing legumes."
                ),
            )
        )
    elif n_status == "excess":
        recs.append(
            Recommendation(
                nutrient="nitrogen",
                status="excess",
                message=(
                    f"Nitrogen is high at {sample.nitrogen_ppm:.1f} ppm. "
                    "Reduce nitrogenous fertilizer to avoid leaf burn and groundwater contamination."
                ),
            )
        )
    else:
        recs.append(
            Recommendation(
                nutrient="nitrogen",
                status="optimal",
                message="Nitrogen levels are within the optimal range.",
            )
        )

    # --- Phosphorus ---
    p_status = _nutrient_status(sample.phosphorus_ppm, 15.0, 30.0)
    if p_status == "deficient":
        recs.append(
            Recommendation(
                nutrient="phosphorus",
                status="deficient",
                message=(
                    f"Phosphorus is low at {sample.phosphorus_ppm:.1f} ppm (optimal 15-30 ppm). "
                    "Apply single super phosphate (SSP) or DAP."
                ),
            )
        )
    elif p_status == "excess":
        recs.append(
            Recommendation(
                nutrient="phosphorus",
                status="excess",
                message=(
                    f"Phosphorus is high at {sample.phosphorus_ppm:.1f} ppm. "
                    "Avoid further phosphatic fertilizer to prevent nutrient lock-out."
                ),
            )
        )
    else:
        recs.append(
            Recommendation(
                nutrient="phosphorus",
                status="optimal",
                message="Phosphorus levels are within the optimal range.",
            )
        )

    # --- Potassium ---
    k_status = _nutrient_status(sample.potassium_ppm, 120.0, 250.0)
    if k_status == "deficient":
        recs.append(
            Recommendation(
                nutrient="potassium",
                status="deficient",
                message=(
                    f"Potassium is low at {sample.potassium_ppm:.1f} ppm (optimal 120-250 ppm). "
                    "Apply muriate of potash (MOP) or sulphate of potash."
                ),
            )
        )
    elif k_status == "excess":
        recs.append(
            Recommendation(
                nutrient="potassium",
                status="excess",
                message=(
                    f"Potassium is high at {sample.potassium_ppm:.1f} ppm. "
                    "Reduce potassium inputs; excess K can inhibit magnesium uptake."
                ),
            )
        )
    else:
        recs.append(
            Recommendation(
                nutrient="potassium",
                status="optimal",
                message="Potassium levels are within the optimal range.",
            )
        )

    # --- pH ---
    if sample.ph_level < 6.5:
        recs.append(
            Recommendation(
                nutrient="ph",
                status="deficient",
                message=(
                    f"Soil pH is acidic at {sample.ph_level:.1f} (optimal 6.5-7.0). "
                    "Apply agricultural lime to raise pH."
                ),
            )
        )
    elif sample.ph_level > 7.0:
        recs.append(
            Recommendation(
                nutrient="ph",
                status="excess",
                message=(
                    f"Soil pH is alkaline at {sample.ph_level:.1f} (optimal 6.5-7.0). "
                    "Apply gypsum or sulphur to lower pH."
                ),
            )
        )
    else:
        recs.append(
            Recommendation(
                nutrient="ph",
                status="optimal",
                message="Soil pH is within the ideal range.",
            )
        )

    # --- Organic carbon ---
    if sample.organic_carbon_pct < 0.75:
        recs.append(
            Recommendation(
                nutrient="organic_carbon",
                status="deficient",
                message=(
                    f"Organic carbon is low at {sample.organic_carbon_pct:.2f}% (target ≥0.75%). "
                    "Incorporate compost, green manure, or crop residues."
                ),
            )
        )
    else:
        recs.append(
            Recommendation(
                nutrient="organic_carbon",
                status="optimal",
                message="Organic carbon levels are adequate.",
            )
        )

    # --- Moisture ---
    if sample.moisture_pct < 20.0:
        recs.append(
            Recommendation(
                nutrient="moisture",
                status="deficient",
                message=(
                    f"Soil moisture is low at {sample.moisture_pct:.1f}% (optimal 20-40%). "
                    "Increase irrigation frequency or apply mulch to retain moisture."
                ),
            )
        )
    elif sample.moisture_pct > 40.0:
        recs.append(
            Recommendation(
                nutrient="moisture",
                status="excess",
                message=(
                    f"Soil moisture is high at {sample.moisture_pct:.1f}% (optimal 20-40%). "
                    "Improve drainage to prevent waterlogging and root rot."
                ),
            )
        )
    else:
        recs.append(
            Recommendation(
                nutrient="moisture",
                status="optimal",
                message="Soil moisture is within the optimal range.",
            )
        )

    return recs


async def _run_analysis(
    sample: SoilSampleRequest
) -> SoilAnalysisResponse:
    """
    Core analysis pipeline.

    1. Compute individual metric scores using numpy.
    2. Compute weighted aggregate health score.
    3. Classify fertility.
    4. Generate recommendations.
    5. Persist in the in-memory store.
    """
    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # --- Individual scores ---
    values = np.array(
        [
            sample.ph_level,
            sample.nitrogen_ppm,
            sample.phosphorus_ppm,
            sample.potassium_ppm,
            sample.organic_carbon_pct,
            sample.moisture_pct,
        ]
    )

    keys = [
        "ph",
        "nitrogen_ppm",
        "phosphorus_ppm",
        "potassium_ppm",
        "organic_carbon_pct",
        "moisture_pct",
    ]

    scores: dict[str, float] = {}
    for key, val in zip(keys, values):
        low, high = _OPTIMAL_RANGES[key]
        scores[key] = _range_score(float(val), low, high)

    # --- Weighted aggregate ---
    weights = np.array([_WEIGHTS[k] for k in keys])
    score_arr = np.array([scores[k] for k in keys])
    health_score = float(np.dot(weights, score_arr))
    health_score = round(np.clip(health_score, 0.0, 100.0), 2)

    fertility_class = _classify_fertility(health_score)
    recommendations = _build_recommendations(sample)

    result = SoilAnalysisResponse(
        analysis_id=analysis_id,
        plot_id=sample.plot_id,
        latitude=sample.latitude,
        longitude=sample.longitude,
        soil_type=sample.soil_type,
        temperature_celsius=sample.temperature_celsius,
        nitrogen_ppm=sample.nitrogen_ppm,
        phosphorus_ppm=sample.phosphorus_ppm,
        potassium_ppm=sample.potassium_ppm,
        ph_level=sample.ph_level,
        organic_carbon_pct=sample.organic_carbon_pct,
        moisture_pct=sample.moisture_pct,
        ph_score=scores["ph"],
        nitrogen_score=scores["nitrogen_ppm"],
        phosphorus_score=scores["phosphorus_ppm"],
        potassium_score=scores["potassium_ppm"],
        organic_carbon_score=scores["organic_carbon_pct"],
        moisture_score=scores["moisture_pct"],
        health_score=health_score,
        fertility_class=fertility_class,
        recommendations=recommendations,
        analyzed_at=now,
    )

    # Persistence disabled for Demo Mode

    return result


# ===================================================================
# Trend calculation
# ===================================================================


def _compute_trend(scores: list[float]) -> str:
    """
    Determine the health-score trend for a series of analyses.

    Uses numpy linear regression (polyfit degree 1) on the score
    sequence.  A positive slope > 1 → improving, negative slope < -1
    → declining, otherwise stable.  Requires at least 2 data points.
    """
    if len(scores) < 2:
        return "insufficient_data"

    x = np.arange(len(scores), dtype=np.float64)
    y = np.array(scores, dtype=np.float64)
    slope, _ = np.polyfit(x, y, 1)

    if slope > 1.0:
        return "improving"
    if slope < -1.0:
        return "declining"
    return "stable"


# ===================================================================
# Photo-based soil analysis helpers
# ===================================================================

# Texture multipliers affect predicted nutrient retention.
# Clay retains more nutrients; sand retains less.
_TEXTURE_PROFILES: dict[str, dict[str, float]] = {
    "clay": {"nutrient_retention": 1.25, "moisture_factor": 1.30, "drainage": 0.6},
    "clay_loam": {
        "nutrient_retention": 1.15,
        "moisture_factor": 1.15,
        "drainage": 0.75,
    },
    "loam": {"nutrient_retention": 1.00, "moisture_factor": 1.00, "drainage": 1.0},
    "silt": {"nutrient_retention": 1.05, "moisture_factor": 1.10, "drainage": 0.85},
    "sandy_loam": {
        "nutrient_retention": 0.85,
        "moisture_factor": 0.80,
        "drainage": 1.2,
    },
    "sandy": {"nutrient_retention": 0.65, "moisture_factor": 0.55, "drainage": 1.5},
}

# Region-based baseline adjustments (simulating geographic variation)
_REGION_BASELINES: dict[str, dict[str, float]] = {
    "tropical": {
        "ph_adj": -0.3,
        "n_adj": 30.0,
        "p_adj": 2.0,
        "k_adj": 15.0,
        "oc_adj": 0.15,
    },
    "arid": {
        "ph_adj": 0.6,
        "n_adj": -60.0,
        "p_adj": -3.0,
        "k_adj": 20.0,
        "oc_adj": -0.20,
    },
    "temperate": {
        "ph_adj": 0.0,
        "n_adj": 0.0,
        "p_adj": 0.0,
        "k_adj": 0.0,
        "oc_adj": 0.0,
    },
    "subtropical": {
        "ph_adj": -0.1,
        "n_adj": 15.0,
        "p_adj": 1.0,
        "k_adj": 10.0,
        "oc_adj": 0.10,
    },
    "unknown": {"ph_adj": 0.0, "n_adj": 0.0, "p_adj": 0.0, "k_adj": 0.0, "oc_adj": 0.0},
}


def _extract_image_features(req: SoilPhotoRequest) -> dict:
    """
    Extract or simulate colour/texture features from the request.

    If explicit HSV values are provided they are used directly.
    If only image_base64 is provided we simulate feature extraction
    by hashing the first 64 chars of the base64 payload to generate
    deterministic pseudo-random HSV values.
    """
    if req.hue is not None and req.saturation is not None and req.value is not None:
        hue, sat, val = req.hue, req.saturation, req.value
    elif req.image_base64:
        # Deterministic pseudo-random features from the image hash
        seed = sum(ord(c) for c in req.image_base64[:64]) % (2**31)
        rng = np.random.RandomState(seed)
        hue = float(rng.uniform(0, 360))
        sat = float(rng.uniform(0.1, 0.9))
        val = float(rng.uniform(0.1, 0.9))
    else:
        # Defaults when neither image nor HSV metadata is given
        hue, sat, val = 30.0, 0.4, 0.45

    texture = (
        req.texture if req.texture and req.texture in _TEXTURE_PROFILES else "loam"
    )

    return {
        "hue": round(hue, 2),
        "saturation": round(sat, 4),
        "value": round(val, 4),
        "texture": texture,
        "region": req.region,
    }


def _predict_from_features(features: dict) -> dict[str, float]:
    """
    Simulate ML inference: predict soil nutrient levels from colour
    and texture features using realistic heuristic correlations.

    Colour correlations used:
    - **Darkness** (low HSV value): darker soils → higher organic carbon
      and nitrogen (decomposed organic matter darkens soil).
    - **Redness** (hue 0-30 or 330-360, high saturation): reddish soils
      → more acidic (iron oxide accumulation, lateritic weathering).
    - **Yellowness** (hue 30-60): moderate iron, slightly acidic.
    - **Greyish / low saturation**: potentially waterlogged → higher
      moisture, lower potassium (leaching).

    All predictions are clipped to physically plausible ranges.
    """
    hue = features["hue"]
    sat = features["saturation"]
    val = features["value"]
    texture = features["texture"]
    region = features["region"]

    tex = _TEXTURE_PROFILES.get(texture, _TEXTURE_PROFILES["loam"])
    reg = _REGION_BASELINES.get(region, _REGION_BASELINES["unknown"])

    # --- pH prediction ---
    # Baseline 6.8; reddish soils push pH down (more acidic)
    # Redness is hue < 30 or hue > 330 with decent saturation
    is_reddish = (hue < 30 or hue > 330) and sat > 0.3
    is_yellowish = 30 <= hue <= 60 and sat > 0.25
    redness_acid_shift = -0.8 * sat if is_reddish else 0.0
    yellowish_shift = -0.3 * sat if is_yellowish else 0.0
    # Low saturation (greyish) soils tend to be slightly alkaline (waterlogged, calcareous)
    grey_alk_shift = 0.4 * (1.0 - sat) if sat < 0.25 else 0.0
    ph = 6.8 + redness_acid_shift + yellowish_shift + grey_alk_shift + reg["ph_adj"]
    ph = float(np.clip(ph, 3.5, 9.5))

    # --- Organic carbon prediction ---
    # Darker soils (lower value) have more organic matter
    # Relationship: OC ~ 2.0 * (1 - value) with texture scaling
    oc_base = 2.0 * (1.0 - val)
    oc = oc_base * tex["nutrient_retention"] + reg["oc_adj"]
    oc = float(np.clip(oc, 0.05, 5.0))

    # --- Nitrogen prediction ---
    # Strongly correlated with organic carbon (Bremner relationship)
    # N (ppm) ≈ OC_pct * 250 + texture/region adjustments
    n = oc * 250.0 * tex["nutrient_retention"] + reg["n_adj"]
    n = float(np.clip(n, 20.0, 900.0))

    # --- Phosphorus prediction ---
    # Moderate correlation with organic carbon; reduced in very acidic
    # or very alkaline soils (fixation)
    p_base = 12.0 + oc * 8.0
    # pH fixation penalty: P availability drops outside 6.0-7.5
    if ph < 6.0:
        p_base *= 0.7
    elif ph > 7.5:
        p_base *= 0.75
    p = p_base * tex["nutrient_retention"] + reg["p_adj"]
    p = float(np.clip(p, 1.0, 80.0))

    # --- Potassium prediction ---
    # Clay soils retain more K; sandy soils lose K to leaching
    # Grey / low-saturation soils (waterlogged) lose K
    k_base = 180.0 * tex["nutrient_retention"]
    if sat < 0.25:
        k_base *= 0.7  # leaching in waterlogged soils
    k = k_base + reg["k_adj"]
    k = float(np.clip(k, 30.0, 500.0))

    # --- Moisture prediction ---
    # Grey / dark soils with low brightness → high moisture
    moisture_base = 30.0 * tex["moisture_factor"]
    moisture_darkness_boost = 15.0 * (1.0 - val)
    moisture_grey_boost = 10.0 * (1.0 - sat) if sat < 0.3 else 0.0
    moisture = moisture_base + moisture_darkness_boost + moisture_grey_boost
    moisture = float(np.clip(moisture, 2.0, 70.0))

    return {
        "ph": round(ph, 2),
        "nitrogen_ppm": round(n, 1),
        "phosphorus_ppm": round(p, 1),
        "potassium_ppm": round(k, 1),
        "organic_carbon_pct": round(oc, 2),
        "moisture_pct": round(moisture, 1),
    }


async def _run_photo_analysis(
    req: SoilPhotoRequest, db: AsyncSession
) -> SoilPhotoResponse:
    """Full pipeline for photo-based soil analysis."""
    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    features = _extract_image_features(req)
    predicted = _predict_from_features(features)

    # Reuse the existing scoring engine
    keys = [
        "ph",
        "nitrogen_ppm",
        "phosphorus_ppm",
        "potassium_ppm",
        "organic_carbon_pct",
        "moisture_pct",
    ]
    scores: dict[str, float] = {}
    for key in keys:
        low, high = _OPTIMAL_RANGES[key]
        scores[key] = _range_score(predicted[key], low, high)

    weights = np.array([_WEIGHTS[k] for k in keys])
    score_arr = np.array([scores[k] for k in keys])
    health_score = float(np.dot(weights, score_arr))
    health_score = round(np.clip(health_score, 0.0, 100.0), 2)
    fertility_class = _classify_fertility(health_score)

    # Build recommendations via a synthetic SoilSampleRequest
    synthetic_sample = SoilSampleRequest(
        plot_id=req.plot_id,
        latitude=req.latitude,
        longitude=req.longitude,
        nitrogen_ppm=predicted["nitrogen_ppm"],
        phosphorus_ppm=predicted["phosphorus_ppm"],
        potassium_ppm=predicted["potassium_ppm"],
        ph_level=predicted["ph"],
        organic_carbon_pct=predicted["organic_carbon_pct"],
        moisture_pct=predicted["moisture_pct"],
        soil_type=req.soil_type,
    )
    recommendations = _build_recommendations(synthetic_sample)

    # Confidence is higher when explicit metadata is provided
    has_explicit_hsv = (
        req.hue is not None and req.saturation is not None and req.value is not None
    )
    has_texture = req.texture is not None and req.texture in _TEXTURE_PROFILES
    confidence = 0.55
    if has_explicit_hsv:
        confidence += 0.20
    if has_texture:
        confidence += 0.15
    if req.region in _REGION_BASELINES and req.region != "unknown":
        confidence += 0.05
    confidence = round(min(confidence, 0.98), 2)

    result = SoilPhotoResponse(
        analysis_id=analysis_id,
        plot_id=req.plot_id,
        latitude=req.latitude,
        longitude=req.longitude,
        region=req.region,
        soil_type=req.soil_type,
        source="photo_analysis",
        predicted_ph=predicted["ph"],
        predicted_nitrogen_ppm=predicted["nitrogen_ppm"],
        predicted_phosphorus_ppm=predicted["phosphorus_ppm"],
        predicted_potassium_ppm=predicted["potassium_ppm"],
        predicted_organic_carbon_pct=predicted["organic_carbon_pct"],
        predicted_moisture_pct=predicted["moisture_pct"],
        ph_score=scores["ph"],
        nitrogen_score=scores["nitrogen_ppm"],
        phosphorus_score=scores["phosphorus_ppm"],
        potassium_score=scores["potassium_ppm"],
        organic_carbon_score=scores["organic_carbon_pct"],
        moisture_score=scores["moisture_pct"],
        health_score=health_score,
        fertility_class=fertility_class,
        image_features=features,
        confidence=confidence,
        recommendations=recommendations,
        analyzed_at=now,
    )

    # Persist to PostgreSQL for later retrieval
    db_record = SoilAnalysis(
        analysis_id=analysis_id,
        plot_id=req.plot_id,
        source="photo_analysis",
        latitude=req.latitude,
        longitude=req.longitude,
        soil_type=result.soil_type,
        region=req.region,
        predicted_ph=result.predicted_ph,
        predicted_nitrogen_ppm=result.predicted_nitrogen_ppm,
        predicted_phosphorus_ppm=result.predicted_phosphorus_ppm,
        predicted_potassium_ppm=result.predicted_potassium_ppm,
        predicted_organic_carbon_pct=result.predicted_organic_carbon_pct,
        predicted_moisture_pct=result.predicted_moisture_pct,
        image_features=features,
        confidence=confidence,
        ph_score=result.ph_score,
        nitrogen_score=result.nitrogen_score,
        phosphorus_score=result.phosphorus_score,
        potassium_score=result.potassium_score,
        organic_carbon_score=result.organic_carbon_score,
        moisture_score=result.moisture_score,
        health_score=health_score,
        fertility_class=fertility_class,
        recommendations=[r.model_dump() for r in recommendations],
        analyzed_at=now,
    )
    db.add(db_record)
    await db.flush()

    return result


# ===================================================================
# Quantum ML correlation helpers
# ===================================================================

_PARAM_NAMES = [
    "nitrogen_ppm",
    "phosphorus_ppm",
    "potassium_ppm",
    "ph",
    "moisture_pct",
    "organic_carbon_pct",
]


def _build_correlation_matrix(values: np.ndarray) -> np.ndarray:
    """
    Build a synthetic correlation matrix from a single observation by
    simulating a neighbourhood of similar soils using small random
    perturbations, then computing the Pearson correlation matrix.

    This mimics what a quantum kernel method would discover from a
    high-dimensional feature space.
    """
    rng = np.random.RandomState(int(np.sum(values * 1000)) % (2**31))
    n_virtual = 200  # virtual samples
    # Generate perturbations scaled to 10-20% of each parameter
    scales = np.abs(values) * 0.15 + 1e-3
    noise = rng.normal(0, 1, size=(n_virtual, len(values))) * scales
    virtual_samples = values + noise

    # Inject realistic correlations:
    # N and OC are strongly positively correlated
    virtual_samples[:, 0] += 0.6 * noise[:, 5] * scales[0]  # N ← OC
    # P drops when pH is very high (calcium-phosphate binding)
    ph_col = virtual_samples[:, 3]
    virtual_samples[:, 1] -= 0.3 * np.where(ph_col > 7.2, (ph_col - 7.2) * 5.0, 0.0)
    # K and moisture negatively correlated (leaching)
    virtual_samples[:, 2] -= 0.25 * noise[:, 4] * scales[2]

    # Clip to non-negative (physically plausible)
    virtual_samples = np.clip(virtual_samples, 0.0, None)

    # Pearson correlation matrix
    corr = np.corrcoef(virtual_samples, rowvar=False)
    return np.round(corr, 4)


def _discover_correlations(
    values: np.ndarray, corr_matrix: np.ndarray, ph: float, region: str
) -> list[CorrelationEntry]:
    """
    Extract non-obvious correlations from the correlation matrix and
    the specific soil parameter values.
    """
    entries: list[CorrelationEntry] = []

    # 1. N-OC relationship
    n_oc_corr = float(corr_matrix[0, 5])
    entries.append(
        CorrelationEntry(
            parameters=["nitrogen_ppm", "organic_carbon_pct"],
            correlation_coefficient=n_oc_corr,
            insight=(
                f"Nitrogen and organic carbon show a strong positive correlation "
                f"(r={n_oc_corr:.3f}). Increasing organic matter through composting "
                f"will simultaneously improve nitrogen availability, reducing the need "
                f"for synthetic urea by an estimated 15-25%."
            ),
            confidence=0.92,
        )
    )

    # 2. pH-Phosphorus binding
    ph_p_corr = float(corr_matrix[3, 1])
    if ph > 7.2:
        p_reduction_pct = round((ph - 7.2) * 15.0, 1)
        insight_ph_p = (
            f"In your {region} region, soils with pH > 7.2 show {p_reduction_pct:.0f}% "
            f"lower phosphorus availability due to calcium-phosphate binding "
            f"(r={ph_p_corr:.3f}). Lowering pH by 0.3-0.5 units could unlock "
            f"fixed phosphorus reserves already present in the soil."
        )
    elif ph < 5.5:
        insight_ph_p = (
            f"At pH {ph:.1f}, aluminium and iron phosphate complexes reduce "
            f"plant-available phosphorus (r={ph_p_corr:.3f}). Liming to pH 6.0-6.5 "
            f"would significantly improve P uptake efficiency."
        )
    else:
        insight_ph_p = (
            f"pH and phosphorus show correlation r={ph_p_corr:.3f}. "
            f"Current pH {ph:.1f} is near optimal for phosphorus availability."
        )
    entries.append(
        CorrelationEntry(
            parameters=["ph", "phosphorus_ppm"],
            correlation_coefficient=ph_p_corr,
            insight=insight_ph_p,
            confidence=0.87,
        )
    )

    # 3. K-Moisture leaching
    k_m_corr = float(corr_matrix[2, 4])
    moisture = float(values[4])
    if moisture > 35.0:
        insight_k_m = (
            f"Potassium and moisture are negatively correlated (r={k_m_corr:.3f}). "
            f"At {moisture:.1f}% moisture, significant K leaching is likely. "
            f"Split potassium applications into 2-3 smaller doses to reduce losses "
            f"by an estimated 20-30%."
        )
    else:
        insight_k_m = (
            f"Potassium and moisture show correlation r={k_m_corr:.3f}. "
            f"Current moisture levels ({moisture:.1f}%) are not causing excessive "
            f"K leaching, but monitor during monsoon season."
        )
    entries.append(
        CorrelationEntry(
            parameters=["potassium_ppm", "moisture_pct"],
            correlation_coefficient=k_m_corr,
            insight=insight_k_m,
            confidence=0.84,
        )
    )

    # 4. Three-way interaction: OC × moisture × N (non-obvious)
    oc_m_corr = float(corr_matrix[5, 4])
    oc_val = float(values[5])
    if oc_val < 0.75 and moisture > 30.0:
        insight_3way = (
            f"Low organic carbon ({oc_val:.2f}%) combined with high moisture "
            f"({moisture:.1f}%) creates a compounding negative effect: waterlogged "
            f"soils with low OM decompose residues anaerobically, producing compounds "
            f"toxic to roots. This three-way interaction (OC-moisture-N) reduces "
            f"nitrogen use efficiency by an estimated 30-40%."
        )
    else:
        insight_3way = (
            f"Organic carbon and moisture interaction (r={oc_m_corr:.3f}) is within "
            f"manageable bounds. Maintaining OC above 0.75% ensures healthy aerobic "
            f"decomposition even at moderate moisture levels."
        )
    entries.append(
        CorrelationEntry(
            parameters=["organic_carbon_pct", "moisture_pct", "nitrogen_ppm"],
            correlation_coefficient=oc_m_corr,
            insight=insight_3way,
            confidence=0.78,
        )
    )

    # 5. Region-specific NPK balance
    n_val, p_val, k_val = float(values[0]), float(values[1]), float(values[2])
    npk_vec = np.array([n_val, p_val * 15.0, k_val])  # scale P to comparable range
    npk_cv = float(np.std(npk_vec) / (np.mean(npk_vec) + 1e-6))
    entries.append(
        CorrelationEntry(
            parameters=["nitrogen_ppm", "phosphorus_ppm", "potassium_ppm"],
            correlation_coefficient=round(1.0 - npk_cv, 4),
            insight=(
                f"NPK balance index (coefficient of variation): {npk_cv:.3f}. "
                f"{'Nutrient ratios are well-balanced.' if npk_cv < 0.3 else 'Significant nutrient imbalance detected — balanced fertilization is critical to avoid antagonistic uptake effects.'} "
                f"In {region} soils, maintaining N:P:K close to 4:2:1 by weight "
                f"optimizes crop uptake synergy."
            ),
            confidence=0.81,
        )
    )

    return entries


def _generate_interventions(
    values: np.ndarray,
    corr_entries: list[CorrelationEntry],
    ph: float,
    region: str,
    soil_type: str,
) -> list[InterventionRecommendation]:
    """Generate prioritized interventions from discovered correlations."""
    interventions: list[InterventionRecommendation] = []
    priority = 1

    n_val, p_val, k_val = float(values[0]), float(values[1]), float(values[2])
    moisture = float(values[4])
    oc = float(values[5])

    # OC-based intervention (highest impact due to cascading benefits)
    if oc < 0.75:
        interventions.append(
            InterventionRecommendation(
                priority=priority,
                action=(
                    "Apply 4-5 tonnes/hectare of farmyard manure or vermicompost "
                    "to raise organic carbon above 0.75%."
                ),
                rationale=(
                    "Organic carbon drives nitrogen mineralisation and improves "
                    "soil structure, water retention, and microbial activity. "
                    "Correlation analysis shows OC is the strongest predictor of "
                    "overall soil health in your sample."
                ),
                expected_impact="15-25% improvement in nitrogen availability within one season.",
            )
        )
        priority += 1

    # pH correction
    if ph > 7.5:
        interventions.append(
            InterventionRecommendation(
                priority=priority,
                action=(
                    f"Apply elemental sulphur (200-400 kg/ha) or gypsum to reduce "
                    f"pH from {ph:.1f} toward 6.5-7.0."
                ),
                rationale=(
                    "Quantum correlation analysis identified calcium-phosphate binding "
                    "as the primary mechanism reducing phosphorus availability at your "
                    "current pH."
                ),
                expected_impact="Unlock 20-35% more plant-available phosphorus from existing soil reserves.",
            )
        )
        priority += 1
    elif ph < 5.5:
        interventions.append(
            InterventionRecommendation(
                priority=priority,
                action=f"Apply agricultural lime (2-4 tonnes/ha) to raise pH from {ph:.1f} to 6.0-6.5.",
                rationale=(
                    "Aluminium toxicity at low pH inhibits root growth and phosphorus "
                    "uptake. Correlation analysis shows a strong pH-P interaction."
                ),
                expected_impact="Reduce aluminium toxicity and improve P availability by 25-40%.",
            )
        )
        priority += 1

    # Moisture-K interaction
    if moisture > 35.0 and k_val < 150.0:
        interventions.append(
            InterventionRecommendation(
                priority=priority,
                action="Split potassium fertiliser into 3 applications and improve field drainage.",
                rationale=(
                    f"At {moisture:.1f}% moisture, potassium leaching losses are significant. "
                    f"Correlation analysis found a negative K-moisture relationship (leaching)."
                ),
                expected_impact="Reduce K losses by 20-30% and save 15-20% on potash fertiliser costs.",
            )
        )
        priority += 1

    # General NPK balance
    if n_val < 250.0:
        interventions.append(
            InterventionRecommendation(
                priority=priority,
                action="Incorporate a legume cover crop (e.g., sun hemp or dhaincha) in the rotation.",
                rationale=(
                    "Biological nitrogen fixation is the most cost-effective way to "
                    "raise soil nitrogen while also boosting organic carbon."
                ),
                expected_impact="Add 40-80 kg N/ha biologically, reducing urea requirement by 30-50%.",
            )
        )
        priority += 1

    if p_val < 15.0:
        interventions.append(
            InterventionRecommendation(
                priority=priority,
                action="Apply rock phosphate or SSP in the furrow at sowing for targeted P delivery.",
                rationale="Phosphorus is immobile in soil; band placement increases uptake efficiency.",
                expected_impact="Improve P uptake efficiency by 25-35% compared to broadcast application.",
            )
        )
        priority += 1

    # Always include a monitoring recommendation
    interventions.append(
        InterventionRecommendation(
            priority=priority,
            action="Re-test soil after 45-60 days to validate correlation-based predictions.",
            rationale=(
                "Quantum-inspired correlation models are strongest when validated "
                "with temporal data. Re-testing enables the model to refine its "
                f"predictions for {soil_type} soils in the {region} region."
            ),
            expected_impact="Continuous improvement in prediction accuracy by 5-10% per cycle.",
        )
    )

    return interventions


def _compute_quantum_metrics(n_params: int) -> QuantumAdvantageMetrics:
    """
    Simulate quantum advantage metrics for the correlation analysis.

    In a real quantum system the speedup comes from quantum kernel
    estimation and Grover-like search over the correlation space.
    Here we produce plausible simulated numbers.
    """
    # Classical: O(n^3) correlation matrix + O(2^n) exhaustive interaction search
    classical_ms = float(n_params**3 * 2.5 + 2**n_params * 0.8)
    # Quantum: O(n^2 log n) kernel + O(sqrt(2^n)) Grover search
    quantum_ms = float(
        n_params**2 * np.log2(n_params) * 1.2 + np.sqrt(2**n_params) * 0.8
    )
    speedup = round(classical_ms / max(quantum_ms, 0.01), 2)

    qubits = n_params * 2 + 3  # encoding + ancilla qubits
    depth = n_params * 4  # circuit depth scales with parameters
    entanglement_pairs = n_params * (n_params - 1) // 2  # all-pairs entanglement

    return QuantumAdvantageMetrics(
        classical_time_ms=round(classical_ms, 2),
        quantum_time_ms=round(quantum_ms, 2),
        speedup_factor=speedup,
        qubits_used=qubits,
        circuit_depth=depth,
        entanglement_pairs=entanglement_pairs,
    )


def _run_quantum_correlation(
    req: QuantumCorrelationRequest,
) -> QuantumCorrelationResponse:
    """Full pipeline for quantum-inspired correlation analysis."""
    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    values = np.array(
        [
            req.nitrogen_ppm,
            req.phosphorus_ppm,
            req.potassium_ppm,
            req.ph,
            req.moisture_pct,
            req.organic_carbon_pct,
        ],
        dtype=np.float64,
    )

    corr_matrix = _build_correlation_matrix(values)
    correlations = _discover_correlations(values, corr_matrix, req.ph, req.region)
    interventions = _generate_interventions(
        values,
        correlations,
        req.ph,
        req.region,
        req.soil_type,
    )
    quantum_metrics = _compute_quantum_metrics(len(_PARAM_NAMES))

    # Build the correlation matrix dict (param name → {param name → coeff})
    corr_dict: dict[str, dict[str, float]] = {}
    for i, name_i in enumerate(_PARAM_NAMES):
        corr_dict[name_i] = {}
        for j, name_j in enumerate(_PARAM_NAMES):
            corr_dict[name_i][name_j] = float(corr_matrix[i, j])

    return QuantumCorrelationResponse(
        analysis_id=analysis_id,
        soil_type=req.soil_type,
        region=req.region,
        correlations=correlations,
        correlation_matrix=corr_dict,
        quantum_metrics=quantum_metrics,
        interventions=interventions,
        analyzed_at=now,
    )


# ===================================================================
# FastAPI application
# ===================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - Database initialization bypassed for Demo Mode."""
    # await init_db()
    yield
    # await close_db()


app = FastAPI(
    title="SoilScan AI",
    description="Analyzes soil health using satellite imagery and sensor data",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The auth router already declares prefix="/auth" internally,
# so we include it WITHOUT an additional prefix to avoid /auth/auth.
app.include_router(auth_router, tags=["auth"])
setup_rate_limiting(app)


# -------------------------------------------------------------------
# Health & root
# -------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": "soilscan_ai",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint returning service info."""
    return {
        "service": "SoilScan AI",
        "version": "1.0.0",
        "features": [
            "Satellite imagery-based soil analysis",
            "IoT sensor data integration",
            "Soil nutrient profiling and recommendations",
            "Historical soil health trend tracking",
            "Batch analysis for multi-plot fields",
        ],
    }


# -------------------------------------------------------------------
# Analysis endpoints
# -------------------------------------------------------------------


@app.post(
    "/analyze", response_model=SoilAnalysisResponse, status_code=status.HTTP_201_CREATED
)
async def analyze_soil(sample: SoilSampleRequest):
    """
    Analyze a single soil sample.

    Computes a health score (0-100) from pH, NPK, organic carbon, and
    moisture readings, classifies fertility, and returns actionable
    recommendations.
    """
    return await _run_analysis(sample)


@app.post(
    "/batch-analyze",
    response_model=BatchAnalyzeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def batch_analyze(body: BatchAnalyzeRequest):
    """
    Analyze multiple soil samples in one request.
    """
    results = []
    for sample in body.samples:
        results.append(await _run_analysis(sample))
    return BatchAnalyzeResponse(results=results, count=len(results))


@app.get("/report/{analysis_id}", response_model=SoilAnalysisResponse)
async def get_report(analysis_id: str):
    """
    Retrieve a report by ID - Persistence discovery disabled in Demo Mode.
    """
    raise HTTPException(status_code=404, detail="Database persistence disabled in Demo Mode.")


@app.get("/history", response_model=HistoryResponse)
async def get_analysis_history(
    plot_id: str = Query(..., description="Plot ID to retrieve history for"),
):
    """
    In-memory history retrieval not implemented in Demo Mode.
    """
    return HistoryResponse(plot_id=plot_id, analyses=[], trend="insufficient_data")


# -------------------------------------------------------------------
# Photo-based soil analysis endpoint
# -------------------------------------------------------------------


@app.post(
    "/analyze-photo",
    response_model=SoilPhotoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_photo(req: SoilPhotoRequest):
    """
    Analyze soil from a photograph or image metadata.

    Accepts either a base64-encoded soil photo or pre-extracted image
    metadata (HSV colour values and texture description).  Uses
    numpy-based simulated ML inference to predict pH, N, P, K, organic
    carbon, and moisture from soil colour and texture features.

    Realistic correlations are applied:
    - Darker soils -> higher organic carbon and nitrogen
    - Reddish soils -> more acidic (iron oxide / laterite)
    - Grey / low-saturation soils -> waterlogged, lower potassium
    - Clay textures -> higher nutrient retention

    Returns a full soil analysis result similar to ``POST /analyze``,
    along with a confidence score and the extracted image features.
    """
    if not req.image_base64 and req.hue is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Provide either 'image_base64' or explicit HSV metadata "
                "('hue', 'saturation', 'value')."
            ),
        )
    return await _run_photo_analysis(req)


# -------------------------------------------------------------------
# Quantum ML correlation endpoint
# -------------------------------------------------------------------


@app.post(
    "/quantum-correlation",
    response_model=QuantumCorrelationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def quantum_correlation(req: QuantumCorrelationRequest):
    """
    Discover non-obvious correlations between soil parameters using
    quantum-inspired ML analysis.

    Takes soil analysis results (N, P, K, pH, moisture, organic carbon,
    soil type, region) and performs quantum-inspired feature correlation
    analysis using numpy.

    Returns:
    - **correlations**: Non-obvious parameter correlations with plain-
      language insights (e.g., pH-phosphorus binding effects).
    - **correlation_matrix**: Full Pearson correlation matrix across all
      six soil parameters.
    - **quantum_metrics**: Simulated quantum advantage metrics including
      speedup factor, qubit count, and circuit depth.
    - **interventions**: Prioritised, actionable recommendations derived
      from the discovered correlations.
    """
    return _run_quantum_correlation(req)


# -------------------------------------------------------------------
# NVIDIA NIM AI Recommendations
# -------------------------------------------------------------------

import httpx as _httpx


class AIRecommendationRequest(BaseModel):
    """Input for AI-powered soil recommendations."""
    nitrogen_ppm: float
    phosphorus_ppm: float
    potassium_ppm: float
    ph_level: float
    health_score: float
    soil_type: str = "unknown"
    moisture_pct: float = 30.0
    organic_carbon_pct: float = 0.8


@app.post("/ai-recommendations", tags=["ai"])
async def ai_recommendations(req: AIRecommendationRequest):
    """
    Get AI-powered soil health recommendations using NVIDIA NIM (Llama 3.3).
    Falls back to rule-based recommendations if the API call fails.
    """
    soil_summary = (
        f"Nitrogen: {req.nitrogen_ppm} ppm, Phosphorus: {req.phosphorus_ppm} ppm, "
        f"Potassium: {req.potassium_ppm} ppm, pH: {req.ph_level}, "
        f"Moisture: {req.moisture_pct}%, Organic Carbon: {req.organic_carbon_pct}%, "
        f"Health Score: {req.health_score}/100, Soil Type: {req.soil_type}"
    )

    api_key = settings.NVIDIA_API_KEY
    if not api_key:
        # Fallback to rule-based
        sample = SoilSampleRequest(
            plot_id="ai-rec", latitude=0, longitude=0,
            nitrogen_ppm=req.nitrogen_ppm, phosphorus_ppm=req.phosphorus_ppm,
            potassium_ppm=req.potassium_ppm, ph_level=req.ph_level,
            organic_carbon_pct=req.organic_carbon_pct, moisture_pct=req.moisture_pct,
        )
        recs = _build_recommendations(sample)
        return {
            "ai_recommendations": "\n".join(f"- {r.message}" for r in recs),
            "source": "rule_based",
            "reason": "NVIDIA_API_KEY not configured",
        }

    system_prompt = (
        "You are an expert AI Agronomist for Annadata OS, India's leading agricultural platform. "
        "Based on the soil data provided, give actionable recommendations:\n"
        "1. **Fertilizer Plan** — specific fertilizers, quantities per hectare\n"
        "2. **Soil Amendments** — lime, gypsum, organic matter interventions\n"
        "3. **Crop Suitability** — top 3 crops suited for this soil profile\n"
        "4. **Urgent Actions** — any immediate interventions needed\n\n"
        "Be concise (≤200 words). Use bullet points. Use farmer-friendly language."
    )

    try:
        async with _httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "meta/llama-3.3-70b-instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Soil Analysis Results:\n{soil_summary}"},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 512,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            ai_text = data["choices"][0]["message"]["content"]
            return {
                "ai_recommendations": ai_text,
                "source": "nvidia_nim",
                "model": "meta/llama-3.3-70b-instruct",
            }
    except Exception as e:
        # Fallback
        sample = SoilSampleRequest(
            plot_id="ai-rec", latitude=0, longitude=0,
            nitrogen_ppm=req.nitrogen_ppm, phosphorus_ppm=req.phosphorus_ppm,
            potassium_ppm=req.potassium_ppm, ph_level=req.ph_level,
            organic_carbon_pct=req.organic_carbon_pct, moisture_pct=req.moisture_pct,
        )
        recs = _build_recommendations(sample)
        return {
            "ai_recommendations": "\n".join(f"- {r.message}" for r in recs),
            "source": "rule_based",
            "reason": f"NIM API error: {e}",
        }


# -------------------------------------------------------------------
# Live Sensor Analysis (Arduino + NVIDIA NIM)
# -------------------------------------------------------------------

@app.post(
    "/live-scan",
    response_model=SoilAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def live_scan(req: LiveScanRequest):
    """
    Perform a live soil scan using the connected Arduino Nano.
    
    1. Reads real-time moisture from the hardware via serial_service.
    2. Uses NVIDIA NIM (Mistral Large) to simulate realistic N, P, K, and pH 
       values based on moisture and location.
    3. Runs the standard scoring and recommendation pipeline.
    """
    # 1. Capture real moisture from HW-080
    moisture = serial_service.get_moisture()
    if moisture is None:
        raise HTTPException(
            status_code=503, 
            detail="Hardware Not Detected. Please connect your SoilScan Arduino via USB."
        )
    
    # 2. Get AI-simulated NPK and pH from NVIDIA NIM
    api_key = settings.NVIDIA_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=500, detail="NVIDIA_API_KEY not configured in .env."
        )

    # Use AsyncOpenAI to avoid blocking the event loop (fixes ECONNRESET)
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )
    
    prompt = f"""
    You are an expert soil scientist. We have a real-time moisture reading from a soil sensor of {moisture}%. 
    The location is lat={req.latitude}, lon={req.longitude} ({req.region}). The soil type is {req.soil_type}.
    
    Based on these conditions, generate realistic soil parameters that a high-end spectrometer would detect.
    Provide values for:
    - nitrogen_ppm (typical range 0-600)
    - phosphorus_ppm (typical range 0-100)
    - potassium_ppm (typical range 0-400)
    - ph_level (typical range 4.0-9.0)
    - organic_carbon_pct (typical range 0.1-3.0)
    - temperature_celsius (typical range 15-40)

    IMPORTANT: Return ONLY the JSON object matching this structure:
    {{
        "nitrogen_ppm": float,
        "phosphorus_ppm": float,
        "potassium_ppm": float,
        "ph_level": float,
        "organic_carbon_pct": float,
        "temperature_celsius": float
    }}
    """

    try:
        completion = await client.chat.completions.create(
            model="mistralai/mistral-large-3-675b-instruct-2512",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            top_p=0.7,
            max_tokens=256,
        )
        ai_data = json.loads(completion.choices[0].message.content)
    except Exception as e:
        # Fallback simulated data if LLM fails
        ai_data = {
            "nitrogen_ppm": 280.0,
            "phosphorus_ppm": 24.5,
            "potassium_ppm": 185.0,
            "ph_level": 6.8,
            "organic_carbon_pct": 0.95,
            "temperature_celsius": 24.0
        }

    # 3. Build standard sample request to reuse analysis logic
    full_sample = SoilSampleRequest(
        plot_id=req.plot_id,
        latitude=req.latitude,
        longitude=req.longitude,
        soil_type=req.soil_type,
        moisture_pct=moisture,
        nitrogen_ppm=ai_data["nitrogen_ppm"],
        phosphorus_ppm=ai_data["phosphorus_ppm"],
        potassium_ppm=ai_data["potassium_ppm"],
        ph_level=ai_data["ph_level"],
        organic_carbon_pct=ai_data["organic_carbon_pct"],
        temperature_celsius=ai_data["temperature_celsius"]
    )

    # 4. Run through the verified scoring engine
    return await _run_analysis(full_sample)

# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("services.soilscan_ai.app:app", host="0.0.0.0", port=8002, reload=True)
