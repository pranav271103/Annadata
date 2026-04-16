"""
Shared database models for Annadata OS.
All services share these common models.

Models are organized by service:
- User, ServiceLog (auth/shared)
- PriceAlert (MSP Mitra)
- SoilAnalysis (SoilScan AI)
- DiseaseDetection (Fasal Rakshak)
- IrrigationPlot, IrrigationEvent, ValveState (Jal Shakti)
- HarvestPlot (Harvest Shakti)
- ChatSession, ChatMessage, FarmerInteraction (Kisaan Sahayak)
- CreditScore (Kisan Credit)
- ConnectionLog, RouteLog (Harvest-to-Cart)
- SeedBatch, SeedVerification, CommunityReport (Beej Suraksha)
- WeatherStation (Mausam Chakra)
"""

import uuid
from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from services.shared.db.session import Base


# ============================================================
# Enums
# ============================================================


class UserRole(str, PyEnum):
    FARMER = "farmer"
    TRADER = "trader"
    RESEARCHER = "researcher"
    ADMIN = "admin"


# ============================================================
# User Model
# ============================================================


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.FARMER, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    # Location
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


# ============================================================
# Service Audit Log
# ============================================================


class ServiceLog(Base):
    __tablename__ = "service_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name = Column(String(100), nullable=False, index=True)
    endpoint = Column(String(255), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    request_method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="service_logs")


# ============================================================
# MSP Mitra — Price Alerts
# ============================================================


class PriceAlert(Base):
    """Stores price alerts for commodity monitoring."""

    __tablename__ = "price_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(50), unique=True, nullable=False, index=True)
    commodity = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=False, index=True)
    target_price = Column(Float, nullable=False)
    direction = Column(String(10), nullable=False)  # "above" or "below"
    status = Column(
        String(20), nullable=False, default="active"
    )  # "active" or "triggered"
    trigger_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "commodity": self.commodity,
            "state": self.state,
            "target_price": self.target_price,
            "direction": self.direction,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
            "trigger_message": self.trigger_message or "",
        }


# ============================================================
# SoilScan AI — Soil Analysis
# ============================================================


class SoilAnalysis(Base):
    """Stores both sensor-based and photo-based soil analyses.

    Uses a 'source' discriminator column:
    - 'sensor_analysis' for SoilAnalysisResponse
    - 'photo_analysis' for SoilPhotoResponse

    Photo-specific fields (predicted_*, image_features, confidence, region)
    are nullable, only populated for photo analyses.
    Sensor-specific fields (nitrogen_ppm, etc.) are also nullable, only
    populated for sensor analyses.
    """

    __tablename__ = "soil_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(100), unique=True, nullable=False, index=True)
    plot_id = Column(String(100), nullable=False, index=True)
    source = Column(String(30), nullable=False, default="sensor_analysis")

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    soil_type = Column(String(50), nullable=True)
    temperature_celsius = Column(Float, nullable=True)

    # Sensor raw readings (sensor_analysis only)
    nitrogen_ppm = Column(Float, nullable=True)
    phosphorus_ppm = Column(Float, nullable=True)
    potassium_ppm = Column(Float, nullable=True)
    ph_level = Column(Float, nullable=True)
    organic_carbon_pct = Column(Float, nullable=True)
    moisture_pct = Column(Float, nullable=True)

    # Photo predicted readings (photo_analysis only)
    predicted_ph = Column(Float, nullable=True)
    predicted_nitrogen_ppm = Column(Float, nullable=True)
    predicted_phosphorus_ppm = Column(Float, nullable=True)
    predicted_potassium_ppm = Column(Float, nullable=True)
    predicted_organic_carbon_pct = Column(Float, nullable=True)
    predicted_moisture_pct = Column(Float, nullable=True)
    region = Column(String(100), nullable=True)
    image_features = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)

    # Computed scores (0-100)
    ph_score = Column(Float, nullable=False)
    nitrogen_score = Column(Float, nullable=False)
    phosphorus_score = Column(Float, nullable=False)
    potassium_score = Column(Float, nullable=False)
    organic_carbon_score = Column(Float, nullable=False)
    moisture_score = Column(Float, nullable=False)

    # Aggregate
    health_score = Column(Float, nullable=False)
    fertility_class = Column(String(20), nullable=False)

    # Recommendations stored as JSON list
    recommendations = Column(JSON, nullable=False, default=list)

    analyzed_at = Column(String(50), nullable=False)  # ISO-8601 timestamp string
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        """Convert to dict matching the original in-memory format."""
        d = {
            "analysis_id": self.analysis_id,
            "plot_id": self.plot_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "soil_type": self.soil_type,
            "ph_score": self.ph_score,
            "nitrogen_score": self.nitrogen_score,
            "phosphorus_score": self.phosphorus_score,
            "potassium_score": self.potassium_score,
            "organic_carbon_score": self.organic_carbon_score,
            "moisture_score": self.moisture_score,
            "health_score": self.health_score,
            "fertility_class": self.fertility_class,
            "recommendations": self.recommendations or [],
            "analyzed_at": self.analyzed_at,
        }
        if self.source == "photo_analysis":
            d.update(
                {
                    "region": self.region,
                    "source": self.source,
                    "predicted_ph": self.predicted_ph,
                    "predicted_nitrogen_ppm": self.predicted_nitrogen_ppm,
                    "predicted_phosphorus_ppm": self.predicted_phosphorus_ppm,
                    "predicted_potassium_ppm": self.predicted_potassium_ppm,
                    "predicted_organic_carbon_pct": self.predicted_organic_carbon_pct,
                    "predicted_moisture_pct": self.predicted_moisture_pct,
                    "image_features": self.image_features or {},
                    "confidence": self.confidence,
                }
            )
        else:
            d.update(
                {
                    "temperature_celsius": self.temperature_celsius,
                    "nitrogen_ppm": self.nitrogen_ppm,
                    "phosphorus_ppm": self.phosphorus_ppm,
                    "potassium_ppm": self.potassium_ppm,
                    "ph_level": self.ph_level,
                    "organic_carbon_pct": self.organic_carbon_pct,
                    "moisture_pct": self.moisture_pct,
                }
            )
        return d


# ============================================================
# Fasal Rakshak — Disease Detection History
# ============================================================


class DiseaseDetection(Base):
    """Stores crop disease detection history entries."""

    __tablename__ = "disease_detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    detection_id = Column(String(100), unique=True, nullable=False, index=True)
    crop = Column(String(100), nullable=False, index=True)
    top_disease = Column(String(200), nullable=True)
    confidence = Column(Float, nullable=True)
    detected_at = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "detection_id": self.detection_id,
            "crop": self.crop,
            "top_disease": self.top_disease,
            "confidence": self.confidence,
            "detected_at": self.detected_at,
        }


# ============================================================
# Jal Shakti — Irrigation Management
# ============================================================


class IrrigationPlot(Base):
    """Registered irrigation plots."""

    __tablename__ = "irrigation_plots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plot_id = Column(String(100), unique=True, nullable=False, index=True)
    farm_id = Column(String(100), nullable=False, index=True)
    crop = Column(String(100), nullable=False)
    area_hectares = Column(Float, nullable=False)
    soil_type = Column(String(50), nullable=False, default="loam")
    irrigation_method = Column(String(50), nullable=False, default="flood")
    current_moisture_pct = Column(Float, nullable=False, default=25.0)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    irrigation_active = Column(Boolean, default=False)
    registered_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "plot_id": self.plot_id,
            "farm_id": self.farm_id,
            "crop": self.crop,
            "area_hectares": self.area_hectares,
            "soil_type": self.soil_type,
            "irrigation_method": self.irrigation_method,
            "current_moisture_pct": self.current_moisture_pct,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "registered_at": self.registered_at.isoformat()
            if self.registered_at
            else None,
            "irrigation_active": self.irrigation_active,
        }


class IrrigationEvent(Base):
    """Records of irrigation water applications."""

    __tablename__ = "irrigation_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plot_id = Column(String(100), nullable=False, index=True)
    farm_id = Column(String(100), nullable=False, index=True)
    crop = Column(String(100), nullable=False)
    area_hectares = Column(Float, nullable=False)
    date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    water_liters = Column(Float, nullable=False)
    water_mm = Column(Float, nullable=False)
    method = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "plot_id": self.plot_id,
            "farm_id": self.farm_id,
            "crop": self.crop,
            "area_hectares": self.area_hectares,
            "date": self.date,
            "water_liters": self.water_liters,
            "water_mm": self.water_mm,
            "method": self.method,
        }


class ValveState(Base):
    """IoT valve status for irrigation plots."""

    __tablename__ = "valve_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plot_id = Column(String(100), unique=True, nullable=False, index=True)
    valve_status = Column(String(20), nullable=False)
    flow_rate_pct = Column(Float, nullable=False)
    battery_level_pct = Column(Float, nullable=False)
    solar_charge_watts = Column(Float, nullable=False)
    last_action = Column(String(20), nullable=False)
    last_action_timestamp = Column(String(50), nullable=False)
    auto_decision_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict:
        return {
            "plot_id": self.plot_id,
            "valve_status": self.valve_status,
            "flow_rate_pct": self.flow_rate_pct,
            "battery_level_pct": self.battery_level_pct,
            "solar_charge_watts": self.solar_charge_watts,
            "last_action": self.last_action,
            "last_action_timestamp": self.last_action_timestamp,
            "auto_decision_reason": self.auto_decision_reason,
        }


# ============================================================
# Harvest Shakti — Plot Registration for Yield Estimation
# ============================================================


class HarvestPlot(Base):
    """Registered plots for yield estimation and harvest window calculation."""

    __tablename__ = "harvest_plots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plot_id = Column(String(100), unique=True, nullable=False, index=True)
    crop = Column(String(100), nullable=False)
    variety = Column(String(100), nullable=True, default="")
    area_hectares = Column(Float, nullable=False)
    sowing_date = Column(Date, nullable=False)
    soil_health_score = Column(Float, nullable=False, default=75.0)
    irrigation_type = Column(String(50), nullable=False, default="flood")
    region = Column(String(100), nullable=True, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# Kisaan Sahayak — Chat Sessions & Farmer Memory
# ============================================================


class ChatSession(Base):
    """Chat sessions for the farming assistant."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages = relationship(
        "ChatMessage", back_populates="session", order_by="ChatMessage.id"
    )


class ChatMessage(Base):
    """Individual messages within a chat session."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(100),
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FarmerInteractionRecord(Base):
    """Farmer interaction memory for pattern analysis."""

    __tablename__ = "farmer_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    farmer_id = Column(String(100), nullable=False, index=True)
    interaction_id = Column(String(100), unique=True, nullable=False, index=True)
    interaction_type = Column(String(100), nullable=False)
    crop_type = Column(String(100), nullable=True)
    disease_detected = Column(String(200), nullable=True)
    severity = Column(String(50), nullable=True)
    location = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    timestamp = Column(String(50), nullable=False)  # ISO-8601 timestamp string
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "interaction_id": self.interaction_id,
            "timestamp": self.timestamp,
            "interaction_type": self.interaction_type,
            "crop_type": self.crop_type,
            "disease_detected": self.disease_detected,
            "severity": self.severity,
            "location": self.location,
            "notes": self.notes,
        }


# ============================================================
# Kisan Credit — Credit Scores
# ============================================================


class CreditScore(Base):
    """Stores calculated credit scores for farmers."""

    __tablename__ = "credit_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score_id = Column(String(100), unique=True, nullable=False, index=True)
    farmer_id = Column(String(100), nullable=False, index=True)
    credit_score = Column(Float, nullable=False)
    grade = Column(String(5), nullable=False)  # A, B, C, D, F
    components = Column(JSON, nullable=False)  # list of ScoreComponent dicts
    loan_eligibility = Column(Boolean, nullable=False)
    max_loan_amount = Column(Float, nullable=False)
    interest_rate_suggestion = Column(Float, nullable=False)
    region = Column(String(100), nullable=True)
    land_area_hectares = Column(Float, nullable=True)
    crop_types = Column(JSON, nullable=False, default=list)  # list of strings
    years_farming = Column(Integer, nullable=True)
    calculated_at = Column(String(50), nullable=False)  # ISO-8601 timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "score_id": self.score_id,
            "farmer_id": self.farmer_id,
            "credit_score": self.credit_score,
            "grade": self.grade,
            "components": self.components or [],
            "loan_eligibility": self.loan_eligibility,
            "max_loan_amount": self.max_loan_amount,
            "interest_rate_suggestion": self.interest_rate_suggestion,
            "region": self.region,
            "land_area_hectares": self.land_area_hectares,
            "crop_types": self.crop_types or [],
            "years_farming": self.years_farming,
            "calculated_at": self.calculated_at,
        }


# ============================================================
# Harvest-to-Cart — Connection & Route Logs
# ============================================================


class ConnectionLog(Base):
    """Logs of farmer-retailer connections."""

    __tablename__ = "connection_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String(50), nullable=False)
    farmer_id = Column(String(100), nullable=False, index=True)
    crop = Column(String(100), nullable=False)
    quantity_tonnes = Column(Float, nullable=False)
    matches = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RouteLog(Base):
    """Logs of optimized logistics routes."""

    __tablename__ = "route_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String(50), nullable=False)
    total_distance_km = Column(Float, nullable=False)
    tonnes = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# Beej Suraksha — Seed Tracking & Community
# ============================================================


class SeedBatch(Base):
    """Registered seed batches with supply chain and blockchain data."""

    __tablename__ = "seed_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    qr_code_id = Column(String(100), unique=True, nullable=False, index=True)
    manufacturer = Column(String(200), nullable=False, index=True)
    manufacturer_verified = Column(Boolean, nullable=False, default=False)
    seed_variety = Column(String(200), nullable=False)
    crop_type = Column(String(100), nullable=False)
    batch_number = Column(String(100), nullable=False)
    manufacture_date = Column(String(20), nullable=False)
    expiry_date = Column(String(20), nullable=False)
    quantity_kg = Column(Float, nullable=False)
    certification_id = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    supply_chain = Column(
        JSON, nullable=False, default=list
    )  # list of checkpoint dicts
    blockchain = Column(JSON, nullable=True)  # list of block dicts, lazily initialized
    registered_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "qr_code_id": self.qr_code_id,
            "manufacturer": self.manufacturer,
            "manufacturer_verified": self.manufacturer_verified,
            "seed_variety": self.seed_variety,
            "crop_type": self.crop_type,
            "batch_number": self.batch_number,
            "manufacture_date": self.manufacture_date,
            "expiry_date": self.expiry_date,
            "quantity_kg": self.quantity_kg,
            "certification_id": self.certification_id,
            "registered_at": self.registered_at.isoformat()
            if self.registered_at
            else None,
            "status": self.status,
            "supply_chain": self.supply_chain or [],
            "blockchain": self.blockchain,
        }


class SeedVerification(Base):
    """Records of seed verification attempts."""

    __tablename__ = "seed_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    verification_id = Column(String(100), unique=True, nullable=False, index=True)
    qr_code_id = Column(String(100), nullable=False, index=True)
    result = Column(
        String(20), nullable=False
    )  # "not_found", "authentic", "suspicious"
    warnings = Column(JSON, nullable=True)  # list of warning strings
    timestamp = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CommunityReport(Base):
    """Community-submitted reports about seed quality issues."""

    __tablename__ = "community_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(100), unique=True, nullable=False, index=True)
    reporter_id = Column(String(100), nullable=False, index=True)
    qr_code_id = Column(String(100), nullable=True, index=True)
    dealer_name = Column(String(200), nullable=False, index=True)
    location = Column(JSON, nullable=False)  # dict with district/state keys
    issue_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    affected_area_hectares = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="submitted")
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "reporter_id": self.reporter_id,
            "qr_code_id": self.qr_code_id,
            "dealer_name": self.dealer_name,
            "location": self.location or {},
            "issue_type": self.issue_type,
            "description": self.description,
            "affected_area_hectares": self.affected_area_hectares,
            "status": self.status,
            "submitted_at": self.submitted_at.isoformat()
            if self.submitted_at
            else None,
        }


# ============================================================
# Mausam Chakra — Weather Station Registry
# ============================================================


class WeatherStation(Base):
    """IoT weather station registry with latest readings."""

    __tablename__ = "weather_stations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String(100), unique=True, nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    last_reading_time = Column(String(50), nullable=True)
    last_ingested_at = Column(String(50), nullable=True)
    readings = Column(JSON, nullable=True)  # dict of latest sensor readings
    quality_flags = Column(JSON, nullable=True)  # list of quality flag strings
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict:
        return {
            "station_id": self.station_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "last_reading_time": self.last_reading_time,
            "last_ingested_at": self.last_ingested_at,
            "readings": self.readings or {},
            "quality_flags": self.quality_flags or [],
            "state": self.state,
            "district": self.district,
            "status": self.status,
        }


class ForecastStats(Base):
    """Simple counter table for forecast generation statistics.

    Uses a single row (singleton pattern) to track the total
    number of forecasts generated. The counter is incremented
    atomically via SQL UPDATE.
    """

    __tablename__ = "forecast_stats"

    id = Column(Integer, primary_key=True, default=1)
    total_forecasts_generated = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ============================================================
# Gamification Models
# ============================================================


class SubscriptionTier(str, PyEnum):
    """Subscription tiers for freemium model."""

    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class QuestStatus(str, PyEnum):
    """Status of user quests."""

    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"


class UserProgress(Base):
    """Tracks user's gamification progress: XP, level, streak.

    This is the core gamification table that stores:
    - Current XP and level
    - Daily streak tracking
    - Subscription tier
    """

    __tablename__ = "user_progress"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    current_xp = Column(Integer, default=0, nullable=False)
    current_level = Column(Integer, default=1, nullable=False)
    total_xp_earned = Column(Integer, default=0, nullable=False)
    current_streak = Column(Integer, default=0, nullable=False)
    longest_streak = Column(Integer, default=0, nullable=False)
    last_active_date = Column(Date, nullable=True)
    subscription_tier = Column(
        Enum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False
    )
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<UserProgress {self.user_id} Level={self.current_level} XP={self.current_xp}>"

    def to_dict(self):
        return {
            "user_id": str(self.user_id),
            "current_xp": self.current_xp,
            "current_level": self.current_level,
            "total_xp_earned": self.total_xp_earned,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "last_active_date": self.last_active_date.isoformat()
            if self.last_active_date
            else None,
            "subscription_tier": self.subscription_tier.value
            if self.subscription_tier
            else "free",
            "subscription_expires_at": self.subscription_expires_at.isoformat()
            if self.subscription_expires_at
            else None,
        }


class XPEvent(Base):
    """Log of XP-earning events for analytics and history.

    Records every XP-earning action for:
    - Analytics and insights
    - XP history display
    - Anti-fraud (detecting XP farming)
    """

    __tablename__ = "xp_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    action_type = Column(String(50), nullable=False, index=True)
    xp_earned = Column(Integer, nullable=False)
    event_data = Column(
        JSON, nullable=True
    )  # Named event_data to avoid SQLAlchemy reserved 'metadata'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<XPEvent {self.action_type} +{self.xp_earned}XP>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "action_type": self.action_type,
            "xp_earned": self.xp_earned,
            "metadata": self.event_data,  # Return as 'metadata' in API response
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserQuest(Base):
    """Tracks daily/weekly quest completion per user.

    Quests are assigned daily and tracked here for completion.
    Quest definitions are stored in-memory in the service.
    """

    __tablename__ = "user_quests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    quest_type = Column(String(20), nullable=False)  # daily, weekly
    quest_id = Column(String(50), nullable=False, index=True)
    status = Column(Enum(QuestStatus), default=QuestStatus.PENDING, nullable=False)
    assigned_date = Column(Date, nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<UserQuest {self.quest_id} status={self.status}>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "quest_type": self.quest_type,
            "quest_id": self.quest_id,
            "status": self.status.value if self.status else "pending",
            "assigned_date": self.assigned_date.isoformat()
            if self.assigned_date
            else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }
