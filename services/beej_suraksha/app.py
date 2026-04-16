"""Beej Suraksha - Seed Purity Verifier with QR-code tracking and AI verification."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
import hashlib
import json
import uuid

import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm.attributes import flag_modified
import logging
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.shared.auth.router import router as auth_router, setup_rate_limiting
from services.shared.config import settings
from services.shared.db.models import CommunityReport, SeedBatch, SeedVerification
from services.shared.db.session import close_db, get_db, init_db

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# Knowledge Base — Genuine Seed Characteristics
# ============================================================

GENUINE_SEED_CHARACTERISTICS: dict[str, dict] = {
    "Pusa Basmati 1121": {
        "crop_type": "rice",
        "manufacturer": "IARI / Multiple Licensed",
        "color": "golden_yellow",
        "size_mm": 8.4,
        "weight_g": 0.025,
        "germination_rate": 85.0,
        "season": "kharif",
        "description": "Extra-long slender grain, aromatic basmati rice variety",
    },
    "IR-64": {
        "crop_type": "rice",
        "manufacturer": "IRRI / Multiple Licensed",
        "color": "light_brown",
        "size_mm": 6.2,
        "weight_g": 0.022,
        "germination_rate": 80.0,
        "season": "kharif",
        "description": "Medium-grain, high-yielding, non-basmati rice variety",
    },
    "HD-2967": {
        "crop_type": "wheat",
        "manufacturer": "IARI",
        "color": "amber",
        "size_mm": 6.5,
        "weight_g": 0.042,
        "germination_rate": 85.0,
        "season": "rabi",
        "description": "High-yielding bread wheat, resistant to yellow rust",
    },
    "PBW-343": {
        "crop_type": "wheat",
        "manufacturer": "PAU Ludhiana",
        "color": "golden_amber",
        "size_mm": 6.0,
        "weight_g": 0.040,
        "germination_rate": 82.0,
        "season": "rabi",
        "description": "Semi-dwarf, high-yielding wheat variety for irrigated timely sown conditions",
    },
    "Bt Cotton (Bollgard II)": {
        "crop_type": "cotton",
        "manufacturer": "Mahyco",
        "color": "dark_brown",
        "size_mm": 9.0,
        "weight_g": 0.10,
        "germination_rate": 75.0,
        "season": "kharif",
        "description": "Transgenic cotton with dual Bt gene for bollworm resistance",
    },
    "Pioneer 30V92": {
        "crop_type": "maize",
        "manufacturer": "Pioneer (Corteva)",
        "color": "orange_yellow",
        "size_mm": 10.0,
        "weight_g": 0.30,
        "germination_rate": 90.0,
        "season": "kharif",
        "description": "High-yielding single-cross maize hybrid for rainfed and irrigated conditions",
    },
    "Pusa Bold": {
        "crop_type": "mustard",
        "manufacturer": "IARI",
        "color": "dark_brown",
        "size_mm": 2.0,
        "weight_g": 0.005,
        "germination_rate": 80.0,
        "season": "rabi",
        "description": "Bold-seeded Indian mustard variety with high oil content (40%)",
    },
    "Kaveri Jadoo": {
        "crop_type": "maize",
        "manufacturer": "Kaveri Seeds",
        "color": "orange",
        "size_mm": 9.5,
        "weight_g": 0.28,
        "germination_rate": 88.0,
        "season": "kharif",
        "description": "Popular maize hybrid with good cob size and grain filling",
    },
    "Rasi RCH-2 Bt": {
        "crop_type": "cotton",
        "manufacturer": "Rasi Seeds",
        "color": "grey_brown",
        "size_mm": 8.5,
        "weight_g": 0.095,
        "germination_rate": 72.0,
        "season": "kharif",
        "description": "Bt cotton hybrid with good fiber quality and bollworm resistance",
    },
    "Nuziveedu Mallika": {
        "crop_type": "cotton",
        "manufacturer": "Nuziveedu Seeds",
        "color": "brown",
        "size_mm": 8.8,
        "weight_g": 0.098,
        "germination_rate": 74.0,
        "season": "kharif",
        "description": "High-yielding Bt cotton hybrid adapted for central and south India",
    },
    "Syngenta NK-6240": {
        "crop_type": "maize",
        "manufacturer": "Syngenta",
        "color": "deep_orange",
        "size_mm": 9.8,
        "weight_g": 0.29,
        "germination_rate": 89.0,
        "season": "kharif",
        "description": "Single-cross maize hybrid with excellent standability and yield potential",
    },
}

# Verified manufacturers
VERIFIED_MANUFACTURERS: dict[str, dict] = {
    "Mahyco": {
        "full_name": "Maharashtra Hybrid Seeds Company",
        "hq": "Jalna, Maharashtra",
        "certification": "ICAR approved",
        "verified": True,
    },
    "Rasi Seeds": {
        "full_name": "Rasi Seeds Pvt. Ltd.",
        "hq": "Attur, Tamil Nadu",
        "certification": "ICAR approved",
        "verified": True,
    },
    "Pioneer (Corteva)": {
        "full_name": "Pioneer Hi-Bred (Corteva Agriscience)",
        "hq": "Hyderabad, Telangana",
        "certification": "ICAR approved",
        "verified": True,
    },
    "Syngenta": {
        "full_name": "Syngenta India Limited",
        "hq": "Pune, Maharashtra",
        "certification": "ICAR approved",
        "verified": True,
    },
    "Nuziveedu Seeds": {
        "full_name": "Nuziveedu Seeds Limited",
        "hq": "Hyderabad, Telangana",
        "certification": "ICAR approved",
        "verified": True,
    },
    "Kaveri Seeds": {
        "full_name": "Kaveri Seed Company Limited",
        "hq": "Secunderabad, Telangana",
        "certification": "ICAR approved",
        "verified": True,
    },
    "IARI": {
        "full_name": "Indian Agricultural Research Institute",
        "hq": "New Delhi",
        "certification": "Government of India",
        "verified": True,
    },
    "PAU Ludhiana": {
        "full_name": "Punjab Agricultural University",
        "hq": "Ludhiana, Punjab",
        "certification": "Government of India",
        "verified": True,
    },
    "IRRI / Multiple Licensed": {
        "full_name": "International Rice Research Institute (licensed)",
        "hq": "Various",
        "certification": "ICAR approved",
        "verified": True,
    },
    "IARI / Multiple Licensed": {
        "full_name": "Indian Agricultural Research Institute (licensed)",
        "hq": "Various",
        "certification": "Government of India",
        "verified": True,
    },
}

# Color feature vectors for simulated image analysis
SEED_COLOR_VECTORS: dict[str, list[float]] = {
    "golden_yellow": [0.85, 0.75, 0.20],
    "light_brown": [0.70, 0.55, 0.30],
    "amber": [0.80, 0.60, 0.15],
    "golden_amber": [0.82, 0.65, 0.18],
    "dark_brown": [0.40, 0.25, 0.10],
    "orange_yellow": [0.90, 0.70, 0.10],
    "orange": [0.92, 0.55, 0.08],
    "deep_orange": [0.88, 0.45, 0.05],
    "grey_brown": [0.50, 0.40, 0.35],
    "brown": [0.55, 0.35, 0.15],
}

# ============================================================
# Stores
# ============================================================

# DB: seed_registry -> SeedBatch table
# DB: verification_records -> SeedVerification table
# DB: community_reports -> CommunityReport table

# ============================================================
# Pydantic Models
# ============================================================


class SeedBatchRegisterRequest(BaseModel):
    manufacturer: str = Field(..., description="Seed manufacturer name")
    seed_variety: str = Field(..., description="Seed variety name")
    crop_type: str = Field(
        ..., description="Crop type (rice, wheat, cotton, maize, mustard)"
    )
    batch_number: str = Field(..., description="Manufacturer batch number")
    manufacture_date: str = Field(..., description="Manufacture date (YYYY-MM-DD)")
    expiry_date: str = Field(..., description="Expiry date (YYYY-MM-DD)")
    quantity_kg: float = Field(..., gt=0, description="Quantity in kilograms")
    certification_id: str = Field(..., description="Government certification ID")


class CommunityReportRequest(BaseModel):
    reporter_id: str = Field(..., description="Reporter user ID")
    qr_code_id: Optional[str] = Field(None, description="QR code ID of the seed batch")
    dealer_name: str = Field(..., description="Seed dealer name")
    location: dict = Field(
        ...,
        description="Location with 'district' and 'state' keys",
    )
    issue_type: str = Field(
        ...,
        description="Issue type: fake_seeds, low_germination, wrong_variety, expired",
    )
    description: str = Field(..., description="Detailed description of the issue")
    affected_area_hectares: float = Field(
        ..., ge=0, description="Affected area in hectares"
    )


class SeedImageAnalysisRequest(BaseModel):
    seed_variety: str = Field(..., description="Expected seed variety name")
    image_description: str = Field(
        ...,
        description="Text description of seed characteristics (color, size, shape, texture)",
    )


# ============================================================
# Helper functions
# ============================================================


def _parse_color_from_description(description: str) -> list[float]:
    """Extract an approximate color vector from a text description."""
    desc_lower = description.lower()
    # Try to match known colors
    for color_name, vector in SEED_COLOR_VECTORS.items():
        if color_name.replace("_", " ") in desc_lower:
            return vector
    # Heuristic fallback based on keywords
    r, g, b = 0.5, 0.5, 0.5
    if "golden" in desc_lower or "yellow" in desc_lower:
        r, g, b = 0.85, 0.70, 0.15
    elif "brown" in desc_lower:
        r, g, b = 0.55, 0.35, 0.15
    elif "orange" in desc_lower:
        r, g, b = 0.90, 0.55, 0.10
    elif "grey" in desc_lower or "gray" in desc_lower:
        r, g, b = 0.50, 0.45, 0.40
    elif "dark" in desc_lower:
        r, g, b = 0.35, 0.25, 0.10
    elif "light" in desc_lower:
        r, g, b = 0.75, 0.65, 0.45
    elif "amber" in desc_lower:
        r, g, b = 0.80, 0.60, 0.15
    return [r, g, b]


def _parse_size_from_description(description: str) -> float:
    """Extract approximate seed size (mm) from description."""
    desc_lower = description.lower()
    # Try to find explicit mm values
    import re

    mm_match = re.search(r"(\d+\.?\d*)\s*mm", desc_lower)
    if mm_match:
        return float(mm_match.group(1))
    # Heuristic keywords
    if "extra long" in desc_lower or "very large" in desc_lower:
        return 10.0
    if "large" in desc_lower or "long" in desc_lower:
        return 8.0
    if "medium" in desc_lower:
        return 6.0
    if "small" in desc_lower or "tiny" in desc_lower:
        return 3.0
    if "bold" in desc_lower:
        return 7.0
    return 6.0  # default medium


def _compute_feature_scores(
    variety_chars: dict,
    description: str,
) -> dict[str, float]:
    """Compute feature matching scores using numpy."""
    # Color score
    expected_color = SEED_COLOR_VECTORS.get(
        variety_chars.get("color", ""), [0.5, 0.5, 0.5]
    )
    observed_color = _parse_color_from_description(description)
    color_expected = np.array(expected_color)
    color_observed = np.array(observed_color)
    color_distance = float(np.linalg.norm(color_expected - color_observed))
    color_score = max(0.0, 100.0 - color_distance * 150.0)

    # Size score
    expected_size = variety_chars.get("size_mm", 6.0)
    observed_size = _parse_size_from_description(description)
    size_diff = abs(expected_size - observed_size) / expected_size
    size_score = max(0.0, 100.0 - size_diff * 200.0)

    # Texture score (keyword matching)
    desc_lower = description.lower()
    texture_keywords = {
        "smooth": 0.8,
        "rough": 0.6,
        "wrinkled": 0.4,
        "glossy": 0.9,
        "matte": 0.7,
        "ridged": 0.5,
        "uniform": 0.85,
        "irregular": 0.3,
        "healthy": 0.9,
        "damaged": 0.2,
        "clean": 0.85,
        "discolored": 0.2,
    }
    texture_scores = [v for k, v in texture_keywords.items() if k in desc_lower]
    texture_score = float(np.mean(texture_scores)) * 100.0 if texture_scores else 60.0

    # Shape score (keyword matching)
    crop_type = variety_chars.get("crop_type", "")
    shape_expectations = {
        "rice": ["slender", "elongated", "long", "grain"],
        "wheat": ["oval", "elliptical", "plump", "rounded"],
        "cotton": ["round", "fuzzy", "ovoid", "cottonseed"],
        "maize": ["flat", "wedge", "dent", "kernel"],
        "mustard": ["round", "spherical", "tiny", "small"],
    }
    expected_shapes = shape_expectations.get(crop_type, [])
    shape_match_count = sum(1 for kw in expected_shapes if kw in desc_lower)
    if expected_shapes:
        shape_score = min(100.0, (shape_match_count / len(expected_shapes)) * 120.0)
    else:
        shape_score = 50.0

    return {
        "color_score": round(color_score, 1),
        "size_score": round(size_score, 1),
        "texture_score": round(texture_score, 1),
        "shape_score": round(shape_score, 1),
    }


async def _get_community_trust_score(qr_code_id: str, db: AsyncSession) -> float:
    """Compute trust score for a seed batch based on community reports."""
    related_result = await db.execute(
        select(CommunityReport).where(CommunityReport.qr_code_id == qr_code_id)
    )
    related = related_result.scalars().all()
    if not related:
        return 100.0  # no complaints = full trust
    negative_types = {"fake_seeds", "low_germination", "wrong_variety", "expired"}
    negatives = sum(1 for r in related if r.issue_type in negative_types)
    score = max(0.0, 100.0 - negatives * 20.0)
    return round(score, 1)


async def _is_flagged_by_community(qr_code_id: str, db: AsyncSession) -> bool:
    """Check if a seed batch has been flagged as fake by the community."""
    related_result = await db.execute(
        select(sa_func.count())
        .select_from(CommunityReport)
        .where(CommunityReport.qr_code_id == qr_code_id)
        .where(CommunityReport.issue_type == "fake_seeds")
    )
    return int(related_result.scalar() or 0) >= 2


async def _get_dealer_reports(dealer_name: str, db: AsyncSession) -> list[dict]:
    """Get all community reports for a given dealer."""
    dealer_lower = dealer_name.strip().lower()
    reports_result = await db.execute(
        select(CommunityReport).where(CommunityReport.dealer_name == dealer_lower)
    )
    return [report.to_dict() for report in reports_result.scalars().all()]


# ============================================================
# Lifespan
# ============================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup resources."""
    await init_db()
    
    # Create a demo seed batch if the table is empty for UX testing
    from services.shared.db.session import async_session_factory
    async with async_session_factory() as db:
        result = await db.execute(select(sa_func.count()).select_from(SeedBatch))
        count = result.scalar()
        if count == 0:
            demo_batch = SeedBatch(
                qr_code_id="BS-DEMO-2025",
                manufacturer="IARI",
                manufacturer_verified=True,
                seed_variety="HD-2967",
                crop_type="wheat",
                batch_number="B-999-DEMO",
                manufacture_date="2025-01-01",
                expiry_date="2026-01-01",
                quantity_kg=50.0,
                certification_id="CERT-DEMO-001",
                status="active",
                supply_chain=[
                    {"checkpoint": "manufacturer", "location": "New Delhi", "timestamp": "2025-01-01T10:00:00Z", "verified": True},
                    {"checkpoint": "released", "location": "Beej Suraksha", "timestamp": "2025-01-02T12:00:00Z", "verified": True}
                ],
            )
            db.add(demo_batch)
            await db.commit()
            print("✓ Demo seed BS-DEMO-2025 created.")
            
    yield
    await close_db()


# ============================================================
# App setup
# ============================================================

app = FastAPI(
    title="Beej Suraksha",
    description="Seed Purity Verifier — QR-code based seed tracking, AI verification, and community reporting",
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

# Auth router already has prefix="/auth" — do NOT add prefix again
app.include_router(auth_router)
setup_rate_limiting(app)


# ============================================================
# Endpoints
# ============================================================


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": "beej_suraksha",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ------ Seed Registration & Verification ------


@app.post("/seed/register")
async def register_seed_batch(
    req: SeedBatchRegisterRequest, db: AsyncSession = Depends(get_db)
):
    """Register a new seed batch and generate a QR code ID for tracking."""
    qr_code_id = f"BS-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:4].upper()}"
    registered_at = datetime.now(timezone.utc).isoformat()

    manufacturer_info = VERIFIED_MANUFACTURERS.get(req.manufacturer)
    manufacturer_verified = manufacturer_info is not None and manufacturer_info.get(
        "verified", False
    )

    batch_info = {
        "qr_code_id": qr_code_id,
        "manufacturer": req.manufacturer,
        "manufacturer_verified": manufacturer_verified,
        "seed_variety": req.seed_variety,
        "crop_type": req.crop_type.lower(),
        "batch_number": req.batch_number,
        "manufacture_date": req.manufacture_date,
        "expiry_date": req.expiry_date,
        "quantity_kg": req.quantity_kg,
        "certification_id": req.certification_id,
        "registered_at": registered_at,
        "status": "active",
    }

    supply_chain = [
        {
            "checkpoint": "manufacturer",
            "location": manufacturer_info["hq"] if manufacturer_info else "Unknown",
            "timestamp": req.manufacture_date + "T00:00:00Z",
            "verified": manufacturer_verified,
        },
        {
            "checkpoint": "quality_testing",
            "location": "Seed Testing Laboratory",
            "timestamp": registered_at,
            "verified": True,
        },
        {
            "checkpoint": "registered",
            "location": "Beej Suraksha Platform",
            "timestamp": registered_at,
            "verified": True,
        },
    ]

    db.add(
        SeedBatch(
            qr_code_id=qr_code_id,
            manufacturer=req.manufacturer,
            manufacturer_verified=manufacturer_verified,
            seed_variety=req.seed_variety,
            crop_type=req.crop_type.lower(),
            batch_number=req.batch_number,
            manufacture_date=req.manufacture_date,
            expiry_date=req.expiry_date,
            quantity_kg=req.quantity_kg,
            certification_id=req.certification_id,
            status="active",
            supply_chain=supply_chain,
            registered_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()

    return {
        "qr_code_id": qr_code_id,
        "batch_info": batch_info,
        "supply_chain": supply_chain,
        "verification_url": f"/seed/verify/{qr_code_id}",
    }


@app.get("/seed/verify/{qr_code_id}")
async def verify_seed_batch(qr_code_id: str, db: AsyncSession = Depends(get_db)):
    """Verify a seed batch by its QR code ID."""
    batch_result = await db.execute(
        select(SeedBatch).where(SeedBatch.qr_code_id == qr_code_id)
    )
    batch = batch_result.scalar_one_or_none()
    if batch is None:
        # Record the failed verification attempt
        db.add(
            SeedVerification(
                verification_id=f"ver-{uuid.uuid4().hex[:8]}",
                qr_code_id=qr_code_id,
                result="not_found",
                warnings=[],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        await db.flush()
        raise HTTPException(
            status_code=404,
            detail=f"Seed batch with QR code '{qr_code_id}' not found in registry. "
            "This seed may be counterfeit or unregistered.",
        )

    now = datetime.now(timezone.utc)
    warnings: list[str] = []

    # Check expiry
    is_expired = False
    try:
        expiry = datetime.strptime(batch.expiry_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        if now > expiry:
            is_expired = True
            warnings.append(
                f"EXPIRED: Seed batch expired on {batch.expiry_date}. "
                "Using expired seeds may lead to poor germination."
            )
    except ValueError:
        warnings.append("Could not parse expiry date for this batch.")

    # Check community flags
    flagged = await _is_flagged_by_community(qr_code_id, db)
    if flagged:
        warnings.append(
            "COMMUNITY FLAGGED: Multiple community reports indicate this batch "
            "may contain fake or substandard seeds. Exercise caution."
        )

    community_trust = await _get_community_trust_score(qr_code_id, db)

    # Determine authenticity
    is_authentic = not is_expired and not flagged and batch.manufacturer_verified

    # Record verification
    db.add(
        SeedVerification(
            verification_id=f"ver-{uuid.uuid4().hex[:8]}",
            qr_code_id=qr_code_id,
            result="authentic" if is_authentic else "suspicious",
            warnings=warnings,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    )
    await db.flush()

    return {
        "is_authentic": is_authentic,
        "batch_info": {
            "qr_code_id": batch.qr_code_id,
            "manufacturer": batch.manufacturer,
            "seed_variety": batch.seed_variety,
            "crop_type": batch.crop_type,
            "batch_number": batch.batch_number,
            "manufacture_date": batch.manufacture_date,
            "expiry_date": batch.expiry_date,
            "quantity_kg": batch.quantity_kg,
            "certification_id": batch.certification_id,
            "registered_at": batch.registered_at.isoformat()
            if batch.registered_at
            else None,
        },
        "manufacturer_verified": batch.manufacturer_verified,
        "supply_chain_history": batch.supply_chain or [],
        "community_trust_score": community_trust,
        "warnings": warnings,
    }


# ------ AI Seed Image Analysis ------


@app.post("/seed/analyze-image")
async def analyze_seed_image(req: SeedImageAnalysisRequest):
    """AI-powered seed image analysis (simulated via text description matching)."""
    variety_chars = GENUINE_SEED_CHARACTERISTICS.get(req.seed_variety)
    if variety_chars is None:
        known = list(GENUINE_SEED_CHARACTERISTICS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Seed variety '{req.seed_variety}' not found in database. "
            f"Known varieties: {known}",
        )

    feature_scores = _compute_feature_scores(variety_chars, req.image_description)

    # Weighted authenticity score
    weights = np.array([0.30, 0.25, 0.25, 0.20])
    scores = np.array(
        [
            feature_scores["color_score"],
            feature_scores["size_score"],
            feature_scores["texture_score"],
            feature_scores["shape_score"],
        ]
    )
    authenticity_score = float(np.dot(weights, scores))
    authenticity_score = round(max(0.0, min(100.0, authenticity_score)), 1)

    # Confidence based on score variance — low variance = high confidence
    score_std = float(np.std(scores))
    confidence = round(max(0.3, min(0.99, 1.0 - score_std / 100.0)), 2)

    # Identify deviations
    deviations: list[str] = []
    if feature_scores["color_score"] < 60:
        deviations.append(
            f"Color mismatch: expected '{variety_chars['color'].replace('_', ' ')}' "
            f"pattern (score: {feature_scores['color_score']})"
        )
    if feature_scores["size_score"] < 60:
        deviations.append(
            f"Size deviation: expected ~{variety_chars['size_mm']}mm "
            f"(score: {feature_scores['size_score']})"
        )
    if feature_scores["texture_score"] < 60:
        deviations.append(
            f"Texture anomaly detected (score: {feature_scores['texture_score']})"
        )
    if feature_scores["shape_score"] < 50:
        deviations.append(
            f"Shape does not match expected {variety_chars['crop_type']} seed profile "
            f"(score: {feature_scores['shape_score']})"
        )

    # Recommendation
    if authenticity_score >= 80:
        recommendation = "PASS — Seeds appear genuine. Safe to use."
    elif authenticity_score >= 55:
        recommendation = (
            "CAUTION — Some characteristics deviate from expected profile. "
            "Recommend physical lab testing before large-scale use."
        )
    else:
        recommendation = (
            "FAIL — Seeds show significant deviations from genuine profile. "
            "Do NOT use. File a complaint with the local agriculture office."
        )

    return {
        "authenticity_score": authenticity_score,
        "confidence": confidence,
        "matched_variety": req.seed_variety,
        "feature_scores": feature_scores,
        "deviations": deviations,
        "recommendation": recommendation,
    }


# ------ Community Reporting ------


@app.post("/community/report")
async def submit_community_report(
    req: CommunityReportRequest, db: AsyncSession = Depends(get_db)
):
    """Submit a community report about seed quality issues."""
    valid_issue_types = {"fake_seeds", "low_germination", "wrong_variety", "expired"}
    if req.issue_type not in valid_issue_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid issue_type '{req.issue_type}'. "
            f"Must be one of: {sorted(valid_issue_types)}",
        )

    report_id = f"RPT-{uuid.uuid4().hex[:8].upper()}"
    submitted_at = datetime.now(timezone.utc).isoformat()

    report = {
        "report_id": report_id,
        "reporter_id": req.reporter_id,
        "qr_code_id": req.qr_code_id,
        "dealer_name": req.dealer_name,
        "location": req.location,
        "issue_type": req.issue_type,
        "description": req.description,
        "affected_area_hectares": req.affected_area_hectares,
        "status": "submitted",
        "submitted_at": submitted_at,
    }
    db.add(
        CommunityReport(
            report_id=report_id,
            reporter_id=req.reporter_id,
            qr_code_id=req.qr_code_id,
            dealer_name=req.dealer_name.strip().lower(),
            location=req.location,
            issue_type=req.issue_type,
            description=req.description,
            affected_area_hectares=req.affected_area_hectares,
            status="submitted",
            submitted_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()

    # Count similar reports (same dealer + same issue type)
    similar_result = await db.execute(
        select(sa_func.count())
        .select_from(CommunityReport)
        .where(CommunityReport.dealer_name == req.dealer_name.strip().lower())
        .where(CommunityReport.issue_type == req.issue_type)
        .where(CommunityReport.report_id != report_id)
    )
    similar_count = int(similar_result.scalar() or 0)

    return {
        "report_id": report_id,
        "status": "submitted",
        "similar_reports_count": similar_count,
    }


@app.get("/community/reports")
async def get_community_reports(
    state: Optional[str] = Query(None, description="Filter by state"),
    district: Optional[str] = Query(None, description="Filter by district"),
    dealer_name: Optional[str] = Query(None, description="Filter by dealer name"),
    issue_type: Optional[str] = Query(None, description="Filter by issue type"),
    min_date: Optional[str] = Query(None, description="Minimum date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """Get community reports with optional filtering."""
    results_query = select(CommunityReport)

    if state:
        state_lower = state.strip().lower()
        results_query = results_query.where(
            CommunityReport.location["state"].astext.ilike(state_lower)
        )

    if district:
        district_lower = district.strip().lower()
        results_query = results_query.where(
            CommunityReport.location["district"].astext.ilike(district_lower)
        )

    if dealer_name:
        dealer_lower = dealer_name.strip().lower()
        results_query = results_query.where(CommunityReport.dealer_name == dealer_lower)

    if issue_type:
        results_query = results_query.where(CommunityReport.issue_type == issue_type)

    if min_date:
        try:
            min_dt = datetime.fromisoformat(min_date)
            results_query = results_query.where(CommunityReport.submitted_at >= min_dt)
        except ValueError:
            logger.warning(f"Invalid min_date format: {min_date}")
            pass


    results = [
        report.to_dict() for report in (await db.execute(results_query)).scalars().all()
    ]

    # Summary stats
    issue_counts: dict[str, int] = {}
    affected_total = 0.0
    for r in results:
        it = r.get("issue_type", "unknown")
        issue_counts[it] = issue_counts.get(it, 0) + 1
        affected_total += r.get("affected_area_hectares", 0.0)

    return {
        "reports": results,
        "summary": {
            "total_reports": len(results),
            "issue_type_breakdown": issue_counts,
            "total_affected_area_hectares": round(affected_total, 2),
        },
    }


@app.get("/community/dealer-rating/{dealer_name}")
async def get_dealer_rating(dealer_name: str, db: AsyncSession = Depends(get_db)):
    """Get aggregated dealer trust score based on community reports."""
    reports = await _get_dealer_reports(dealer_name, db)

    if not reports:
        return {
            "dealer_name": dealer_name,
            "trust_score": 100.0,
            "total_reports": 0,
            "positive_reports": 0,
            "negative_reports": 0,
            "verified_batches": 0,
            "recommendation": "No reports found. Dealer has no community feedback yet.",
        }

    negative_types = {"fake_seeds", "low_germination", "wrong_variety", "expired"}
    negative_reports = sum(1 for r in reports if r.get("issue_type") in negative_types)
    positive_reports = len(reports) - negative_reports

    # Trust score: starts at 100, decreases with negative reports
    # Each negative report reduces score; fake_seeds reports are weighted more
    fake_count = sum(1 for r in reports if r.get("issue_type") == "fake_seeds")
    other_negative = negative_reports - fake_count
    trust_score = max(
        0.0,
        100.0 - fake_count * 25.0 - other_negative * 10.0 + positive_reports * 2.0,
    )
    trust_score = round(min(100.0, trust_score), 1)

    # Count verified batches sold by this dealer
    dealer_lower = dealer_name.strip().lower()
    verified_result = await db.execute(
        select(sa_func.count())
        .select_from(SeedBatch)
        .where(SeedBatch.manufacturer == dealer_lower)
        .where(SeedBatch.manufacturer_verified.is_(True))
    )
    verified_batches = int(verified_result.scalar() or 0)

    # Recommendation
    if trust_score >= 80:
        recommendation = "TRUSTED — Dealer has a good track record. Safe to purchase."
    elif trust_score >= 50:
        recommendation = (
            "MODERATE — Some complaints registered. Verify seed packaging, "
            "certification, and QR codes before purchasing."
        )
    else:
        recommendation = (
            "WARNING — Multiple complaints against this dealer. "
            "Avoid purchasing and report to local agriculture department."
        )

    return {
        "dealer_name": dealer_name,
        "trust_score": trust_score,
        "total_reports": len(reports),
        "positive_reports": positive_reports,
        "negative_reports": negative_reports,
        "verified_batches": verified_batches,
        "recommendation": recommendation,
    }


# ------ Catalog & Stats ------


@app.get("/seed/catalog")
async def get_seed_catalog():
    """List all known genuine seed varieties with expected characteristics."""
    catalog = []
    for variety_name, chars in GENUINE_SEED_CHARACTERISTICS.items():
        catalog.append(
            {
                "variety_name": variety_name,
                "crop_type": chars["crop_type"],
                "manufacturer": chars["manufacturer"],
                "color": chars["color"].replace("_", " "),
                "size_mm": chars["size_mm"],
                "weight_g": chars["weight_g"],
                "germination_rate_pct": chars["germination_rate"],
                "season": chars["season"],
                "description": chars["description"],
            }
        )
    return {"varieties": catalog, "total": len(catalog)}


@app.get("/stats")
async def get_statistics(db: AsyncSession = Depends(get_db)):
    """Aggregate statistics for the Beej Suraksha platform."""
    registered_result = await db.execute(select(sa_func.count()).select_from(SeedBatch))
    total_registered = int(registered_result.scalar() or 0)
    verifications_result = await db.execute(
        select(sa_func.count()).select_from(SeedVerification)
    )
    total_verifications = int(verifications_result.scalar() or 0)
    reports_result = await db.execute(
        select(sa_func.count()).select_from(CommunityReport)
    )
    total_reports = int(reports_result.scalar() or 0)

    # Count unique flagged dealers (dealers with 2+ fake_seeds reports)
    fake_reports_result = await db.execute(
        select(CommunityReport.dealer_name).where(
            CommunityReport.issue_type == "fake_seeds"
        )
    )
    dealer_fake_counts: dict[str, int] = {}
    for dealer in fake_reports_result.scalars().all():
        dn = dealer.strip().lower()
        dealer_fake_counts[dn] = dealer_fake_counts.get(dn, 0) + 1
    flagged_dealers = sum(1 for count in dealer_fake_counts.values() if count >= 2)

    # Average trust score across all dealers with reports
    all_dealers_result = await db.execute(select(CommunityReport.dealer_name))
    all_dealers = {
        dealer.strip().lower() for dealer in all_dealers_result.scalars().all()
    }

    if all_dealers:
        trust_scores = []
        negative_types = {"fake_seeds", "low_germination", "wrong_variety", "expired"}
        for dealer in all_dealers:
            d_reports_result = await db.execute(
                select(CommunityReport).where(CommunityReport.dealer_name == dealer)
            )
            d_reports = [
                report.to_dict() for report in d_reports_result.scalars().all()
            ]
            neg = sum(1 for r in d_reports if r.get("issue_type") in negative_types)
            pos = len(d_reports) - neg
            fake = sum(1 for r in d_reports if r.get("issue_type") == "fake_seeds")
            other_neg = neg - fake
            score = max(
                0.0, min(100.0, 100.0 - fake * 25.0 - other_neg * 10.0 + pos * 2.0)
            )
            trust_scores.append(score)
        avg_trust = round(float(np.mean(trust_scores)), 1)
    else:
        avg_trust = 100.0

    return {
        "total_registered_batches": total_registered,
        "total_verifications": total_verifications,
        "total_reports": total_reports,
        "flagged_dealers_count": flagged_dealers,
        "avg_trust_score": avg_trust,
    }


# ============================================================
# Blockchain Supply Chain Tracking — Models
# ============================================================


class BlockchainTransactionRequest(BaseModel):
    qr_code_id: str = Field(..., description="QR code ID of the seed batch")
    transaction_type: str = Field(
        ...,
        description="Transaction type: manufactured, quality_checked, distributed, sold, delivered",
    )
    actor_name: str = Field(
        ..., description="Name of the actor performing the transaction"
    )
    actor_role: str = Field(
        ...,
        description="Role of the actor: manufacturer, distributor, dealer, farmer",
    )
    location: str = Field(..., description="Location where the transaction occurred")
    notes: str = Field(default="", description="Optional notes about the transaction")


# ============================================================
# Blockchain Helper Functions
# ============================================================


def _compute_block_hash(previous_hash: str, timestamp: str, data: dict) -> str:
    """Compute SHA-256 hash for a blockchain block."""
    block_string = previous_hash + timestamp + json.dumps(data, sort_keys=True)
    return hashlib.sha256(block_string.encode()).hexdigest()


def _get_blockchain(qr_code_id: str) -> list[dict]:
    """Get or initialize the blockchain for a seed batch."""
    return []


def _verify_chain_integrity(blockchain: list[dict]) -> tuple[bool, list[str]]:
    """Verify the integrity of a blockchain by recalculating all hashes."""
    issues: list[str] = []
    if not blockchain:
        return True, []

    # Verify genesis block
    genesis = blockchain[0]
    expected_genesis_hash = _compute_block_hash(
        genesis["previous_hash"], genesis["timestamp"], genesis["data"]
    )
    if genesis["hash"] != expected_genesis_hash:
        issues.append(f"Block 0 (genesis): hash mismatch — possible tampering detected")

    # Verify subsequent blocks
    for i in range(1, len(blockchain)):
        block = blockchain[i]
        prev_block = blockchain[i - 1]

        # Check previous_hash linkage
        if block["previous_hash"] != prev_block["hash"]:
            issues.append(
                f"Block {i}: previous_hash does not match hash of block {i - 1} — chain broken"
            )

        # Recalculate hash
        expected_hash = _compute_block_hash(
            block["previous_hash"], block["timestamp"], block["data"]
        )
        if block["hash"] != expected_hash:
            issues.append(f"Block {i}: hash mismatch — possible tampering detected")

    return len(issues) == 0, issues


# ============================================================
# Blockchain Supply Chain Endpoints
# ============================================================


@app.post("/blockchain/add-transaction")
async def add_blockchain_transaction(
    req: BlockchainTransactionRequest, db: AsyncSession = Depends(get_db)
):
    """Add a blockchain transaction to a seed's supply chain.

    Creates a new block with SHA-256 hash linked to the previous block,
    ensuring tamper-evident supply chain tracking from manufacturer to farmer.
    """
    valid_transaction_types = {
        "manufactured",
        "quality_checked",
        "distributed",
        "sold",
        "delivered",
    }
    if req.transaction_type not in valid_transaction_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transaction_type '{req.transaction_type}'. "
            f"Must be one of: {sorted(valid_transaction_types)}",
        )

    valid_actor_roles = {"manufacturer", "distributor", "dealer", "farmer"}
    if req.actor_role not in valid_actor_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid actor_role '{req.actor_role}'. "
            f"Must be one of: {sorted(valid_actor_roles)}",
        )

    batch_result = await db.execute(
        select(SeedBatch).where(SeedBatch.qr_code_id == req.qr_code_id)
    )
    batch = batch_result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=f"Seed batch with QR code '{req.qr_code_id}' not found in registry.",
        )

    if not batch.blockchain:
        genesis_data = {
            "transaction_type": "genesis",
            "actor_name": batch.manufacturer or "Unknown",
            "actor_role": "manufacturer",
            "location": "Beej Suraksha Platform",
            "notes": "Genesis block — seed batch registered on platform",
            "seed_variety": batch.seed_variety or "",
            "batch_number": batch.batch_number or "",
        }
        genesis_timestamp = (
            batch.registered_at.isoformat()
            if batch.registered_at
            else datetime.now(timezone.utc).isoformat()
        )
        genesis_hash = _compute_block_hash("0" * 64, genesis_timestamp, genesis_data)
        batch.blockchain = [
            {
                "block_number": 0,
                "timestamp": genesis_timestamp,
                "previous_hash": "0" * 64,
                "hash": genesis_hash,
                "data": genesis_data,
            }
        ]
        flag_modified(batch, "blockchain")

    blockchain = batch.blockchain
    previous_block = blockchain[-1]
    previous_hash = previous_block["hash"]

    timestamp = datetime.now(timezone.utc).isoformat()
    data = {
        "transaction_type": req.transaction_type,
        "actor_name": req.actor_name,
        "actor_role": req.actor_role,
        "location": req.location,
        "notes": req.notes,
    }

    block_hash = _compute_block_hash(previous_hash, timestamp, data)
    new_block = {
        "block_number": len(blockchain),
        "timestamp": timestamp,
        "previous_hash": previous_hash,
        "hash": block_hash,
        "data": data,
    }
    blockchain.append(new_block)
    flag_modified(batch, "blockchain")

    # Also append to the legacy supply_chain list for backward compatibility
    batch.supply_chain = batch.supply_chain or []
    batch.supply_chain.append(
        {
            "checkpoint": req.transaction_type,
            "location": req.location,
            "timestamp": timestamp,
            "verified": True,
            "actor": req.actor_name,
            "actor_role": req.actor_role,
        }
    )
    flag_modified(batch, "supply_chain")
    await db.flush()

    is_valid, issues = _verify_chain_integrity(blockchain)

    return {
        "transaction": new_block,
        "chain_length": len(blockchain),
        "chain_integrity": {
            "is_valid": is_valid,
            "issues": issues,
        },
        "qr_code_id": req.qr_code_id,
    }


@app.get("/blockchain/verify-chain/{qr_code_id}")
async def verify_blockchain_chain(qr_code_id: str, db: AsyncSession = Depends(get_db)):
    """Verify the integrity of a seed's supply chain blockchain.

    Recalculates all SHA-256 hashes and checks chain linkage to detect
    any tampering or data corruption in the supply chain history.
    """
    batch_result = await db.execute(
        select(SeedBatch).where(SeedBatch.qr_code_id == qr_code_id)
    )
    batch = batch_result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=f"Seed batch with QR code '{qr_code_id}' not found in registry.",
        )

    blockchain = batch.blockchain or []
    is_valid, issues = _verify_chain_integrity(blockchain)

    return {
        "qr_code_id": qr_code_id,
        "chain_valid": is_valid,
        "total_blocks": len(blockchain),
        "tampering_detected": len(issues) > 0,
        "issues": issues,
        "transaction_history": blockchain,
    }


@app.get("/blockchain/trace/{qr_code_id}")
async def trace_seed_journey(qr_code_id: str, db: AsyncSession = Depends(get_db)):
    """Full traceability from manufacturer to farmer.

    Returns the complete journey of a seed batch through the supply chain
    with visualization-ready data including timeline, actors, and locations.
    """
    batch_result = await db.execute(
        select(SeedBatch).where(SeedBatch.qr_code_id == qr_code_id)
    )
    batch = batch_result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=f"Seed batch with QR code '{qr_code_id}' not found in registry.",
        )

    blockchain = batch.blockchain or []
    is_valid, issues = _verify_chain_integrity(blockchain)

    # Build journey visualization data
    journey_steps: list[dict] = []
    actor_set: set[str] = set()
    location_set: set[str] = set()

    for block in blockchain:
        data = block["data"]
        step = {
            "step_number": block["block_number"],
            "timestamp": block["timestamp"],
            "transaction_type": data.get("transaction_type", "unknown"),
            "actor_name": data.get("actor_name", "Unknown"),
            "actor_role": data.get("actor_role", "unknown"),
            "location": data.get("location", "Unknown"),
            "notes": data.get("notes", ""),
            "block_hash": block["hash"][:16] + "...",
            "verified": is_valid,
        }
        journey_steps.append(step)
        actor_set.add(data.get("actor_name", "Unknown"))
        location_set.add(data.get("location", "Unknown"))

    # Determine current status based on last transaction
    last_transaction = (
        blockchain[-1]["data"].get("transaction_type", "unknown")
        if blockchain
        else "unknown"
    )
    status_map = {
        "genesis": "Registered on platform",
        "manufactured": "At manufacturer",
        "quality_checked": "Quality verified",
        "distributed": "In distribution",
        "sold": "Sold to dealer/farmer",
        "delivered": "Delivered to end user",
    }
    current_status = status_map.get(last_transaction, "Unknown")

    # Compute journey duration
    if len(blockchain) >= 2:
        first_ts = blockchain[0]["timestamp"]
        last_ts = blockchain[-1]["timestamp"]
        try:
            first_dt = datetime.fromisoformat(first_ts)
            last_dt = datetime.fromisoformat(last_ts)
            duration_hours = round((last_dt - first_dt).total_seconds() / 3600, 1)
        except (ValueError, TypeError):
            duration_hours = 0.0
    else:
        duration_hours = 0.0

    return {
        "qr_code_id": qr_code_id,
        "seed_variety": batch.seed_variety or "Unknown",
        "batch_number": batch.batch_number or "Unknown",
        "manufacturer": batch.manufacturer or "Unknown",
        "current_status": current_status,
        "chain_integrity": {
            "is_valid": is_valid,
            "tampering_detected": len(issues) > 0,
            "issues": issues,
        },
        "journey": {
            "total_steps": len(journey_steps),
            "duration_hours": duration_hours,
            "unique_actors": sorted(actor_set),
            "unique_locations": sorted(location_set),
            "steps": journey_steps,
        },
    }


if __name__ == "__main__":
    uvicorn.run(
        "services.beej_suraksha.app:app", host="0.0.0.0", port=8010, reload=True
    )
