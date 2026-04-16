"""
Kisan Credit Score - Fintech for Farmers.

Builds a comprehensive credit score for farmers based on historical yields,
land productivity, weather risk, and market volatility.  The score drives
loan eligibility, maximum loan amount, and interest rate suggestions.

All scoring uses numpy for vectorised math (weighted scoring, z-scores,
coefficient of variation).  Results are stored in-memory so they can be
retrieved without an external database.
"""

from __future__ import annotations
import logging


import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.shared.auth.router import router as auth_router, setup_rate_limiting
from services.shared.config import settings
from services.shared.db.models import CreditScore
from services.shared.db.session import close_db, get_db, init_db

# ---------------------------------------------------------------------------
# Credit score store
# ---------------------------------------------------------------------------
# DB: _score_store -> CreditScore table

# ---------------------------------------------------------------------------
# Regional weather risk mapping for major Indian states
# ---------------------------------------------------------------------------
# Risk factor 0.0 (no risk) → 1.0 (extreme risk).
# Based on historical flood/drought/cyclone frequency data.
_REGIONAL_WEATHER_RISK: dict[str, float] = {
    "andhra_pradesh": 0.65,
    "arunachal_pradesh": 0.55,
    "assam": 0.75,
    "bihar": 0.70,
    "chhattisgarh": 0.40,
    "goa": 0.35,
    "gujarat": 0.60,
    "haryana": 0.35,
    "himachal_pradesh": 0.45,
    "jharkhand": 0.50,
    "karnataka": 0.50,
    "kerala": 0.70,
    "madhya_pradesh": 0.40,
    "maharashtra": 0.55,
    "manipur": 0.50,
    "meghalaya": 0.55,
    "mizoram": 0.45,
    "nagaland": 0.45,
    "odisha": 0.75,
    "punjab": 0.30,
    "rajasthan": 0.65,
    "sikkim": 0.40,
    "tamil_nadu": 0.60,
    "telangana": 0.50,
    "tripura": 0.55,
    "uttar_pradesh": 0.55,
    "uttarakhand": 0.50,
    "west_bengal": 0.65,
}

# ---------------------------------------------------------------------------
# Average yields by crop type (quintals per hectare) — Indian averages
# ---------------------------------------------------------------------------
_AVERAGE_YIELDS: dict[str, float] = {
    "rice": 26.0,
    "wheat": 35.0,
    "maize": 30.0,
    "cotton": 5.0,
    "sugarcane": 700.0,
    "soybean": 12.0,
    "mustard": 13.0,
    "groundnut": 18.0,
    "jowar": 10.0,
    "bajra": 13.0,
    "tur_dal": 8.0,
    "chana": 10.0,
    "potato": 230.0,
    "onion": 180.0,
    "tomato": 250.0,
    "jute": 25.0,
    "tea": 20.0,
    "coffee": 9.0,
    "rubber": 15.0,
    "coconut": 100.0,
}

# ---------------------------------------------------------------------------
# Crop MSP data (₹ per quintal, 2024-25 Kharif/Rabi season)
# Used for market volatility estimation
# ---------------------------------------------------------------------------
_CROP_MSP: dict[str, float] = {
    "rice": 2300.0,
    "wheat": 2275.0,
    "maize": 2090.0,
    "cotton": 7121.0,
    "sugarcane": 315.0,
    "soybean": 4892.0,
    "mustard": 5650.0,
    "groundnut": 6377.0,
    "jowar": 3180.0,
    "bajra": 2500.0,
    "tur_dal": 7000.0,
    "chana": 5440.0,
}

# Historical price volatility (coefficient of variation over last 5 years)
_CROP_VOLATILITY: dict[str, float] = {
    "rice": 0.08,
    "wheat": 0.10,
    "maize": 0.15,
    "cotton": 0.25,
    "sugarcane": 0.05,
    "soybean": 0.20,
    "mustard": 0.18,
    "groundnut": 0.22,
    "jowar": 0.12,
    "bajra": 0.14,
    "tur_dal": 0.28,
    "chana": 0.22,
    "potato": 0.35,
    "onion": 0.45,
    "tomato": 0.50,
    "jute": 0.15,
    "tea": 0.12,
    "coffee": 0.18,
    "rubber": 0.20,
    "coconut": 0.10,
}

# ---------------------------------------------------------------------------
# Regional soil degradation risk (0-1, higher = worse)
# ---------------------------------------------------------------------------
_SOIL_DEGRADATION_RISK: dict[str, float] = {
    "andhra_pradesh": 0.50,
    "assam": 0.45,
    "bihar": 0.55,
    "chhattisgarh": 0.35,
    "gujarat": 0.55,
    "haryana": 0.60,
    "karnataka": 0.45,
    "kerala": 0.30,
    "madhya_pradesh": 0.40,
    "maharashtra": 0.50,
    "odisha": 0.45,
    "punjab": 0.65,
    "rajasthan": 0.70,
    "tamil_nadu": 0.50,
    "telangana": 0.45,
    "uttar_pradesh": 0.55,
    "uttarakhand": 0.35,
    "west_bengal": 0.50,
}

# ---------------------------------------------------------------------------
# Grade thresholds & loan parameters
# ---------------------------------------------------------------------------
_GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (80.0, "A"),
    (65.0, "B"),
    (50.0, "C"),
    (35.0, "D"),
    (0.0, "F"),
]

# Base loan amount per hectare (₹)
_BASE_LOAN_PER_HECTARE: float = 75_000.0

# Credit multiplier by grade
_CREDIT_MULTIPLIER: dict[str, float] = {
    "A": 2.5,
    "B": 2.0,
    "C": 1.5,
    "D": 1.0,
    "F": 0.0,
}

# Interest rate suggestions by grade (annual %)
_INTEREST_RATE: dict[str, float] = {
    "A": 4.0,
    "B": 7.0,
    "C": 9.0,
    "D": 12.0,
    "F": 0.0,  # Not eligible
}


# ===================================================================
# Pydantic request / response schemas
# ===================================================================



# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CreditScoreRequest(BaseModel):
    """Input payload for a single farmer credit score calculation."""

    farmer_id: str
    historical_yields: list[float] = Field(
        ..., min_length=1, description="Historical crop yields in quintals per hectare"
    )
    land_area_hectares: float = Field(gt=0, description="Total cultivable land area")
    crop_types: list[str] = Field(
        ..., min_length=1, description="List of crops grown by the farmer"
    )
    region: str = Field(
        ..., description="Indian state in snake_case (e.g. 'madhya_pradesh')"
    )
    years_farming: int = Field(ge=0, description="Total years of farming experience")


class ScoreComponent(BaseModel):
    """Breakdown of an individual scoring component."""

    name: str
    score: float
    max_score: float
    details: str


class CreditScoreResponse(BaseModel):
    """Full result returned after credit score calculation."""

    score_id: str
    farmer_id: str
    credit_score: float
    grade: str
    components: list[ScoreComponent]
    loan_eligibility: bool
    max_loan_amount: float
    interest_rate_suggestion: float
    region: str
    land_area_hectares: float
    crop_types: list[str]
    years_farming: int
    calculated_at: str  # ISO-8601 timestamp


class BatchCreditScoreRequest(BaseModel):
    """Wrapper for batch credit score calculation."""

    farmers: list[CreditScoreRequest]


class BatchCreditScoreResponse(BaseModel):
    """Wrapper for batch calculation results."""

    results: list[CreditScoreResponse]
    count: int


class AggregateStats(BaseModel):
    """Aggregate statistics across all calculated scores."""

    total_scores_calculated: int
    average_score: float
    grade_distribution: dict[str, int]
    avg_loan_amount: float


class RegionalRiskAssessment(BaseModel):
    """Risk profile for a specific region."""

    region: str
    weather_risk: float
    market_volatility: float
    soil_degradation_risk: float
    overall_risk: float
    risk_category: Literal["low", "moderate", "high", "very_high"]
    recommendations: list[str]


# ===================================================================
# Scoring helpers (numpy-based)
# ===================================================================


def _assign_grade(score: float) -> str:
    """Map a 0-100 credit score to a letter grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _yield_consistency_score(historical_yields: list[float]) -> tuple[float, str]:
    """
    Score yield consistency (0-25) based on coefficient of variation.

    Lower CV → higher consistency → higher score.
    A CV of 0 gives a perfect 25; CV >= 0.5 gives 0.
    Uses numpy for mean, std, and clipping.
    """
    yields = np.array(historical_yields, dtype=np.float64)
    mean_yield = float(np.mean(yields))
    if mean_yield <= 0:
        return 0.0, "Insufficient yield data (mean yield ≤ 0)"

    std_yield = float(np.std(yields, ddof=1)) if len(yields) > 1 else 0.0
    cv = std_yield / mean_yield

    # Linear mapping: CV=0 → 25, CV>=0.5 → 0
    raw = 25.0 * (1.0 - cv / 0.5)
    score = float(np.clip(raw, 0.0, 25.0))
    score = round(score, 2)

    details = (
        f"Mean yield: {mean_yield:.1f} q/ha, Std dev: {std_yield:.1f}, "
        f"CV: {cv:.3f} ({len(yields)} seasons)"
    )
    return score, details


def _land_productivity_score(
    historical_yields: list[float],
    land_area_hectares: float,
    crop_types: list[str],
) -> tuple[float, str]:
    """
    Score land productivity (0-25) by comparing yield per hectare against
    the regional/national average for the primary crop.

    Uses numpy z-score approach: how many standard deviations above/below
    the national average the farmer's mean yield sits.
    """
    yields = np.array(historical_yields, dtype=np.float64)
    farmer_avg_yield = float(np.mean(yields))

    # Use the first crop type as primary for benchmark comparison
    primary_crop = crop_types[0].lower().strip() if crop_types else "rice"
    national_avg = _AVERAGE_YIELDS.get(primary_crop, 20.0)

    # Assume a national std dev of ~30% of the average
    national_std = national_avg * 0.30
    if national_std < 1e-6:
        national_std = 1.0

    # Z-score: how many std devs above/below average
    z = (farmer_avg_yield - national_avg) / national_std

    # Map z-score to 0-25:  z=-2 → 0, z=0 → 12.5, z=+2 → 25
    raw = 12.5 + (z * 6.25)
    score = float(np.clip(raw, 0.0, 25.0))
    score = round(score, 2)

    # Productivity factor for loan calculation
    productivity_ratio = farmer_avg_yield / national_avg if national_avg > 0 else 1.0

    details = (
        f"Avg yield: {farmer_avg_yield:.1f} q/ha vs national avg "
        f"{national_avg:.1f} q/ha for {primary_crop} "
        f"(z-score: {z:+.2f}, productivity ratio: {productivity_ratio:.2f}), "
        f"land area: {land_area_hectares:.1f} ha"
    )
    return score, details


def _weather_risk_score(region: str) -> tuple[float, str]:
    """
    Score weather risk (0-25) based on historical weather data for the
    farmer's region.

    Lower regional risk → higher score.  Uses the pre-built regional
    weather risk mapping for Indian states.
    """
    region_key = region.lower().strip()
    risk_factor = _REGIONAL_WEATHER_RISK.get(region_key, 0.50)

    # Invert: low risk_factor → high score
    # risk_factor=0 → 25, risk_factor=1.0 → 0
    raw = 25.0 * (1.0 - risk_factor)
    score = float(np.clip(raw, 0.0, 25.0))
    score = round(score, 2)

    risk_pct = risk_factor * 100
    details = (
        f"Region '{region}' has a weather risk factor of {risk_factor:.2f} "
        f"({risk_pct:.0f}% historical disaster probability). "
        f"Score inversely proportional to risk."
    )
    return score, details


def _market_diversification_score(
    crop_types: list[str],
) -> tuple[float, str]:
    """
    Score market diversification (0-25) based on number of different
    crops and their combined market volatility.

    More crops → better diversification → higher score.
    Lower average portfolio volatility → higher score.
    Uses numpy for portfolio volatility computation.
    """
    unique_crops = list(set(c.lower().strip() for c in crop_types))
    n_crops = len(unique_crops)

    # --- Crop count component (0-15) ---
    # 1 crop → 3, 2 → 6, 3 → 9, 4 → 12, 5+ → 15
    count_score = float(np.clip(n_crops * 3.0, 0.0, 15.0))

    # --- Portfolio volatility component (0-10) ---
    # Gather individual crop volatilities
    volatilities = np.array(
        [_CROP_VOLATILITY.get(c, 0.20) for c in unique_crops], dtype=np.float64
    )

    if n_crops > 1:
        # Simple diversification benefit: average volatility reduced by
        # sqrt(n) factor (like a naive portfolio diversification)
        avg_vol = float(np.mean(volatilities))
        portfolio_vol = avg_vol / np.sqrt(n_crops)
    else:
        portfolio_vol = float(volatilities[0]) if len(volatilities) > 0 else 0.20

    # Map portfolio volatility to score: vol=0 → 10, vol>=0.3 → 0
    vol_score = 10.0 * (1.0 - portfolio_vol / 0.3)
    vol_score = float(np.clip(vol_score, 0.0, 10.0))

    total_score = round(count_score + vol_score, 2)
    total_score = float(np.clip(total_score, 0.0, 25.0))

    details = (
        f"{n_crops} unique crop(s): {', '.join(unique_crops)}. "
        f"Avg crop volatility: {float(np.mean(volatilities)):.3f}, "
        f"Portfolio volatility (diversified): {portfolio_vol:.3f}. "
        f"Count component: {count_score:.1f}/15, "
        f"Volatility component: {vol_score:.1f}/10"
    )
    return total_score, details


async def _calculate_credit_score(
    req: CreditScoreRequest, db: AsyncSession
) -> CreditScoreResponse:
    """
    Core credit scoring pipeline.

    1. Compute four component scores using numpy.
    2. Sum to get total credit score (0-100).
    3. Assign grade.
    4. Determine loan eligibility, max loan amount, and interest rate.
    5. Persist in the in-memory store.
    """
    score_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # --- Component scoring ---
    yield_score, yield_details = _yield_consistency_score(req.historical_yields)
    prod_score, prod_details = _land_productivity_score(
        req.historical_yields, req.land_area_hectares, req.crop_types
    )
    weather_score, weather_details = _weather_risk_score(req.region)
    market_score, market_details = _market_diversification_score(req.crop_types)

    components = [
        ScoreComponent(
            name="yield_consistency",
            score=yield_score,
            max_score=25.0,
            details=yield_details,
        ),
        ScoreComponent(
            name="land_productivity",
            score=prod_score,
            max_score=25.0,
            details=prod_details,
        ),
        ScoreComponent(
            name="weather_risk",
            score=weather_score,
            max_score=25.0,
            details=weather_details,
        ),
        ScoreComponent(
            name="market_diversification",
            score=market_score,
            max_score=25.0,
            details=market_details,
        ),
    ]

    # --- Aggregate score ---
    component_scores = np.array(
        [yield_score, prod_score, weather_score, market_score], dtype=np.float64
    )
    credit_score = float(np.sum(component_scores))

    # Experience bonus: up to 5 extra points for 10+ years of farming,
    # but cap the total at 100
    experience_bonus = float(np.clip(req.years_farming * 0.5, 0.0, 5.0))
    credit_score = float(np.clip(credit_score + experience_bonus, 0.0, 100.0))
    credit_score = round(credit_score, 2)

    grade = _assign_grade(credit_score)

    # --- Loan calculation ---
    loan_eligible = grade in ("A", "B", "C", "D")
    credit_multiplier = _CREDIT_MULTIPLIER.get(grade, 0.0)

    # Productivity factor: farmer's avg yield / national avg
    primary_crop = req.crop_types[0].lower().strip() if req.crop_types else "rice"
    national_avg = _AVERAGE_YIELDS.get(primary_crop, 20.0)
    farmer_avg = float(np.mean(req.historical_yields))
    productivity_factor = farmer_avg / national_avg if national_avg > 0 else 1.0
    productivity_factor = float(np.clip(productivity_factor, 0.5, 3.0))

    max_loan = (
        req.land_area_hectares
        * _BASE_LOAN_PER_HECTARE
        * productivity_factor
        * credit_multiplier
    )
    max_loan = round(max_loan, 2)

    interest_rate = _INTEREST_RATE.get(grade, 0.0)

    result = CreditScoreResponse(
        score_id=score_id,
        farmer_id=req.farmer_id,
        credit_score=credit_score,
        grade=grade,
        components=components,
        loan_eligibility=loan_eligible,
        max_loan_amount=max_loan,
        interest_rate_suggestion=interest_rate,
        region=req.region,
        land_area_hectares=req.land_area_hectares,
        crop_types=req.crop_types,
        years_farming=req.years_farming,
        calculated_at=now,
    )

    # Persist for later retrieval
    db.add(
        CreditScore(
            score_id=score_id,
            farmer_id=req.farmer_id,
            credit_score=credit_score,
            grade=grade,
            components=[component.model_dump() for component in components],
            loan_eligibility=loan_eligible,
            max_loan_amount=max_loan,
            interest_rate_suggestion=interest_rate,
            region=req.region,
            land_area_hectares=req.land_area_hectares,
            crop_types=req.crop_types,
            years_farming=req.years_farming,
            calculated_at=now,
        )
    )
    await db.flush()

    return result


# ===================================================================
# FastAPI application
# ===================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup resources."""
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="Kisan Credit Score",
    description=(
        "Fintech for Farmers — builds a credit score based on historical yields, "
        "land productivity, weather risk, and market volatility"
    ),
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
        "service": "kisan_credit",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint returning service info."""
    return {
        "service": "Kisan Credit Score",
        "version": "1.0.0",
        "features": [
            "Farmer credit scoring based on yield history",
            "Land productivity benchmarking against national averages",
            "Regional weather risk assessment",
            "Market diversification and volatility analysis",
            "Loan eligibility and interest rate suggestions",
            "Batch credit score calculation",
            "Aggregate scoring statistics",
        ],
    }


# -------------------------------------------------------------------
# Credit score endpoints
# -------------------------------------------------------------------


@app.post(
    "/credit-score/calculate",
    response_model=CreditScoreResponse,
    status_code=status.HTTP_201_CREATED,
)
async def calculate_credit_score(
    req: CreditScoreRequest, db: AsyncSession = Depends(get_db)
):
    """
    Calculate a farmer's credit score.

    Evaluates four components (yield consistency, land productivity,
    weather risk, market diversification) each scored 0-25, producing
    a total score of 0-100.  Also computes loan eligibility, maximum
    loan amount, and a suggested interest rate.
    """
    return await _calculate_credit_score(req, db)


@app.get("/credit-score/{score_id}", response_model=CreditScoreResponse)
async def get_credit_score(score_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a previously calculated credit score by its ID.

    Returns 404 if the score_id is not found in the in-memory store.
    """
    result = await db.execute(
        select(CreditScore).where(CreditScore.score_id == score_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credit score '{score_id}' not found.",
        )
    return record.to_dict()


@app.post(
    "/credit-score/batch",
    response_model=BatchCreditScoreResponse,
    status_code=status.HTTP_201_CREATED,
)
async def batch_calculate(
    body: BatchCreditScoreRequest, db: AsyncSession = Depends(get_db)
):
    """
    Batch-calculate credit scores for multiple farmers.

    Each farmer's data is processed independently and stored.
    """
    if not body.farmers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one farmer record is required.",
        )

    results = [await _calculate_credit_score(f, db) for f in body.farmers]
    return BatchCreditScoreResponse(results=results, count=len(results))


@app.get("/credit-score/stats", response_model=AggregateStats)
async def get_aggregate_stats(db: AsyncSession = Depends(get_db)):
    """
    Get aggregate statistics across all calculated credit scores.

    Returns total count, average score, grade distribution, and average
    loan amount.
    """
    total_result = await db.execute(select(sa_func.count()).select_from(CreditScore))
    total_scores = int(total_result.scalar() or 0)
    if total_scores == 0:
        return AggregateStats(
            total_scores_calculated=0,
            average_score=0.0,
            grade_distribution={},
            avg_loan_amount=0.0,
        )

    scores_result = await db.execute(select(CreditScore.credit_score))
    scores = np.array(scores_result.scalars().all(), dtype=np.float64)
    loans_result = await db.execute(select(CreditScore.max_loan_amount))
    loan_amounts = np.array(loans_result.scalars().all(), dtype=np.float64)
    grades_result = await db.execute(select(CreditScore.grade))
    grades = grades_result.scalars().all()

    grade_dist = dict(Counter(grades))
    # Ensure all grades present
    for g in ("A", "B", "C", "D", "F"):
        grade_dist.setdefault(g, 0)

    return AggregateStats(
        total_scores_calculated=total_scores,
        average_score=round(float(np.mean(scores)), 2),
        grade_distribution=grade_dist,
        avg_loan_amount=round(float(np.mean(loan_amounts)), 2),
    )


# -------------------------------------------------------------------
# Regional risk assessment
# -------------------------------------------------------------------


@app.get("/risk-assessment/{region}", response_model=RegionalRiskAssessment)
async def get_regional_risk(region: str):
    """
    Get a comprehensive risk assessment for a specific Indian region.

    Evaluates weather risk, market volatility (average across crops
    commonly grown in the region), soil degradation risk, and combines
    them into an overall risk score with actionable recommendations.
    """
    region_key = region.lower().strip()

    weather_risk = _REGIONAL_WEATHER_RISK.get(region_key)
    if weather_risk is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Region '{region}' not found. Use snake_case Indian state names "
                f"(e.g. 'madhya_pradesh', 'uttar_pradesh')."
            ),
        )

    # Average market volatility across all tracked crops
    all_vols = np.array(list(_CROP_VOLATILITY.values()), dtype=np.float64)
    market_volatility = round(float(np.mean(all_vols)), 3)

    soil_risk = _SOIL_DEGRADATION_RISK.get(region_key, 0.45)

    # Overall risk: weighted combination
    risk_weights = np.array([0.45, 0.25, 0.30], dtype=np.float64)
    risk_values = np.array(
        [weather_risk, market_volatility, soil_risk], dtype=np.float64
    )
    overall_risk = round(float(np.dot(risk_weights, risk_values)), 3)

    # Categorise
    if overall_risk >= 0.7:
        risk_category: Literal["low", "moderate", "high", "very_high"] = "very_high"
    elif overall_risk >= 0.5:
        risk_category = "high"
    elif overall_risk >= 0.3:
        risk_category = "moderate"
    else:
        risk_category = "low"

    # Build recommendations based on risk profile
    recommendations: list[str] = []

    if weather_risk >= 0.6:
        recommendations.append(
            "High weather risk — consider crop insurance (PMFBY) and invest in "
            "irrigation infrastructure to mitigate drought/flood impact."
        )
    if weather_risk >= 0.4:
        recommendations.append(
            "Moderate-to-high weather exposure — diversify planting dates and use "
            "weather-resistant crop varieties."
        )

    if market_volatility >= 0.20:
        recommendations.append(
            "Market volatility is significant — grow a mix of MSP-backed staples "
            "and cash crops to stabilise income."
        )

    if soil_risk >= 0.5:
        recommendations.append(
            "Soil degradation risk is elevated — adopt conservation tillage, "
            "organic amendments, and crop rotation to preserve soil health."
        )
    if soil_risk >= 0.3:
        recommendations.append(
            "Periodically test soil health and use micro-nutrient supplements "
            "based on deficiency reports."
        )

    if overall_risk >= 0.5:
        recommendations.append(
            "Overall risk is high — lenders should consider smaller loan tranches "
            "with seasonal disbursement tied to crop milestones."
        )
    else:
        recommendations.append(
            "Overall risk is manageable — the region supports standard agricultural "
            "lending products with competitive interest rates."
        )

    return RegionalRiskAssessment(
        region=region,
        weather_risk=round(weather_risk, 3),
        market_volatility=market_volatility,
        soil_degradation_risk=round(soil_risk, 3),
        overall_risk=overall_risk,
        risk_category=risk_category,
        recommendations=recommendations,
    )


# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("services.kisan_credit.app:app", host="0.0.0.0", port=8008, reload=True)
