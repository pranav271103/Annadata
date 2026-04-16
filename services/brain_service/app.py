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

# Load environment variables
load_dotenv()


# Service Registry
SERVICES = {
    "msp": "http://localhost:8001",
    "soil": "http://localhost:8002",
    "weather": "http://localhost:8011",
    "kisaan": "http://localhost:8006",
}

# NVIDIA Configuration
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1"


# Add root to path for shared modules
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT)

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
            resp = await client.get(f"{SERVICES['msp']}/predict/{crop}", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return f"Market Data for {crop}: Final Price: Rs {data.get('final_price', 'N/A')}, Confidence: {data.get('confidence', 'N/A')}"
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
    return ""

async def get_soil_context(latitude: float, longitude: float) -> str:
    """Fetch latest soil health for a location."""
    try:
        async with httpx.AsyncClient() as client:
            # Placeholder: In production, we'd lookup by lat/long or user_id
            resp = await client.get(f"{SERVICES['soil']}/history", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    latest = data[0]
                    return f"Soil Health: Score {latest.get('health_score', 'N/A')}, Fertility: {latest.get('fertility_status', 'N/A')}"
    except Exception as e:
        logger.error(f"Error fetching soil data: {e}")
    return ""

async def get_weather_context(lat: str, lon: str) -> str:
    """Fetch current weather and advisory."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{SERVICES['weather']}/current?lat={lat}&lon={lon}", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return f"Weather: {data.get('temp_c', 'N/A')}°C, {data.get('condition', 'N/A')}. Advisory: {data.get('advisory', 'N/A')}"
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
                headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                json={
                    "model": "nvidia/llama-3.1-405b", # Using high-fidelity model for the brain
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
                timeout=30.0
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"NVIDIA Brain call failed: {e}")
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
    # In a real agentic loop, we'd use an LLM to decide which tools to use.
    # Here we perform proactive gathering for demonstration.
    
    # Placeholder for crop detection logic (could also be the LLM)
    crop = "wheat" if "wheat" in request.message.lower() else "rice" if "rice" in request.message.lower() else None
    
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
