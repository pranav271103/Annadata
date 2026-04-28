import os
import sys
import logging
import asyncio
import httpx
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Query
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Add root to path for shared modules
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from services.shared.config import settings

# Service Registry (Injected from SharedSettings)
SERVICES = {
    "msp": settings.MSP_MITRA_URL,
    "soil": settings.SOILSCAN_AI_URL,
    "weather": settings.MAUSAM_CHAKRA_URL,
    "kisaan": settings.KISAAN_SAHAYAK_URL,
}

# NVIDIA Configuration
NVIDIA_API_KEY = settings.NVIDIA_API_KEY
NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize shared HTTP client
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("Brain Service starting up...")
    yield
    # Shutdown: Close HTTP client
    await app.state.http_client.aclose()
    logger.info("Brain Service shutting down...")

app = FastAPI(
    title="Annadata OS Brain - Centralized AI Orchestrator",
    description="Agentic brain that unifies expertise from all Annadata microservices",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Service Clients (Tools)
# ============================================================

async def get_market_context(crop: str) -> str:
    """Fetch market prices and predictions for a crop."""
    try:
        async with httpx.AsyncClient() as client:
            # Correct path for msp_mitra: needs commodity and state
            # Using 'Rajasthan' as default state for prediction context
            resp = await client.get(f"{SERVICES['msp']}/predict?commodity={crop}&state=Rajasthan", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                # Handle list of forecasts or single object
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                price = data.get("predicted_price") or data.get("price") or "N/A"
                conf = data.get("confidence") or "High"
                return f"Market Data for {crop}: Estimated Price: Rs {price}, Confidence: {conf}"
    except Exception as e:
        logger.error(f"Error fetching market data for {crop}: {e}")
    return ""

async def get_soil_context(latitude: float, longitude: float) -> str:
    """Fetch latest soil health for a location."""
    try:
        async with httpx.AsyncClient() as client:
            # soilscan_ai returns HistoryResponse { analyses: [] }
            resp = await client.get(f"{SERVICES['soil']}/history", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                analyses = data.get("analyses", [])
                if analyses:
                    latest = analyses[0]
                    return f"Soil Health: Score {latest.get('health_score', 'N/A')}, Fertility: {latest.get('fertility_status', 'N/A')}"
                elif isinstance(data, list) and len(data) > 0:
                    latest = data[0]
                    return f"Soil Health: Score {latest.get('health_score', 'N/A')}"
    except Exception as e:
        logger.error(f"Error fetching soil data: {e}")
    return ""

async def get_weather_context(lat: str, lon: str) -> str:
    """Fetch current weather and advisory."""
    try:
        async with httpx.AsyncClient() as client:
            # mausam_chakra uses village codes. Defaulting to Ludhiana for general context.
            resp = await client.get(f"{SERVICES['weather']}/weather/current/PB-LDH-001", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return f"Weather: {data.get('temperature_c', 'N/A')}°C, {data.get('conditions', 'N/A')}. Advisory: {data.get('advisory', 'N/A')}"
    except Exception as e:
        logger.error(f"Error fetching weather data: {e}")
    return ""

async def get_kisaan_dossier(crop: str) -> str:
    """Fetch knowledge base grounding for a crop."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{SERVICES['kisaan']}/dossier/{crop}", timeout=5.0)
            if resp.status_code == 200:
                return resp.json().get("context", "")
    except Exception as e:
        logger.error(f"Error fetching kisaan dossier: {e}")
    return ""


async def call_nvidia_brain(user_message: str, context: str, history: List[Dict] = [], language: str = "en") -> str:

    """Unified NVIDIA NIM caller with grounding context."""
    if not NVIDIA_API_KEY:
        return "NVIDIA API Key missing. Please configure NVIDIA_API_KEY."

    system_prompt = f"""
    You are the Annadata Brain, a highly intelligent agricultural assistant.
    Use the following AGRICULTURAL CONTEXT to answer the farmer's query accurately.
    CONTEXT:
    {context}
    
    GUIDELINES:
    1. Be empathetic and professional.
    2. Provide actionable advice for the specific crop and weather conditions.
    3. Respond in {language}.
    4. Format as a concise, WhatsApp-friendly message with bold headers and emojis.
    """

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-5:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{NVIDIA_ENDPOINT}/chat/completions",
                headers={
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                    "Accept": "application/json",
                },
                json={
                    "model": "meta/llama-3.3-70b-instruct",
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
                timeout=30.0
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                logger.error(f"NVIDIA API responded with {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"NVIDIA Brain call failed: {e}", exc_info=True)
    return "The brain is currently offline. Please try again later."


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: str = "en"
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ChatResponse(BaseModel):
    response: str
    intent: str
    crop: Optional[str] = None
    actions: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    model: str = "Annadata-Brain-v1"

# ============================================================
# Endpoints
# ============================================================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "brain_service", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.post("/chat", response_model=ChatResponse)
async def chat_orchestrator(request: ChatRequest):
    """
    Main entry point for unified AI advisory.
    Aggregates data from sub-services and uses NVIDIA NIM for the response.
    """
    logger.info(f"Brain processing request: {request.message[:50]}...")
    
    # 1. Gather context from sub-services
    KNOWN_CROPS = ["wheat", "rice", "maize", "sugarcane", "cotton", "mustard", "potato", "apple", "blueberry", "cherry", "grape", "orange", "peach", "pepper"]
    msg_low = request.message.lower()
    crop = next((c for c in KNOWN_CROPS if c in msg_low), None)
    
    context_parts = []
    
    # Parallel context gathering
    tasks = []
    if crop:
        tasks.append(get_market_context(crop))
        tasks.append(get_kisaan_dossier(crop))
    if request.latitude and request.longitude:

        tasks.append(get_soil_context(request.latitude, request.longitude))
        tasks.append(get_weather_context(str(request.latitude), str(request.longitude)))
        
    if tasks:
        results = await asyncio.gather(*tasks)
        context_parts.extend([r for r in results if r])
        
    full_context = "\n".join(context_parts)
    
    # 2. Call the Brain (NVIDIA NIM)
    response_text = await call_nvidia_brain(
        user_message=request.message,
        context=full_context,
        language=request.language
    )
    
    return ChatResponse(
        response=response_text,
        intent="general_advisory",
        crop=crop,
        actions=[{"title": "View Market Trends", "url": "/market"}],
        model="Annadata-Brain-v3.3-Grounded"
    )



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8013)
