"""Kisaan Sahayak - AI-powered agricultural knowledge assistant for farmers.

Integrates NVIDIA NIM (Llama 3.3) for natural-language advisory while
retaining rule-based knowledge retrieval as grounding context and fallback.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import math
import random
import uvicorn
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import delete, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.shared.auth.router import router as auth_router, setup_rate_limiting
from services.shared.config import settings
from services.shared.db.models import ChatMessage, ChatSession, FarmerInteractionRecord
from services.shared.db.session import close_db, get_db, init_db

# ---------------------------------------------------------------------------
# NVIDIA NIM Setup (OpenAI-compatible)
# ---------------------------------------------------------------------------
_NVIDIA_AVAILABLE = False
_NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1"
_NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"

_NVIDIA_API_KEY = settings.NVIDIA_API_KEY or os.environ.get("NVIDIA_API_KEY", "")
if _NVIDIA_API_KEY:
    _NVIDIA_AVAILABLE = True
    logger.info("NVIDIA NIM initialised - Annadata Support AI enabled.")
else:
    logger.warning("NVIDIA_API_KEY not set — falling back to rule-based chat.")

import httpx


# No special rate limiter needed for NIM trial keys usually, but we could add one if needed.


# ---------------------------------------------------------------------------
# System prompt for NVIDIA-enhanced chat
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are **Annadata Support AI**, a warm and deeply knowledgeable **Personal Agricultural Expert**. 
Your mission is to provide support, precise advisory, and empathetic guidance to Indian farmers.

## Your Personality
- You are not just an AI; you are a partner in the farmer's journey. Use a warm, human, and encouraging tone.
- You represent **Team Annadata**. Always use "We" instead of "I".
- Avoid technical jargon and overly structured markdown headers. 
- **NO Markdown Headers**: Do not use "##" or "###". Use **Bold Text** for emphasis and bullet points for lists.

## Knowledge & Priorities
- You have access to a [GROUNDING CONTEXT] with official Annadata data (Calendars, Fertilizers, Pests).
- ALWAYS prioritize this [GROUNDING CONTEXT] over general knowledge.
- If context is missing, provide the best local advice for Indian conditions.

## Advisory Style
1. **Be Conversational**: Talk like a human agronomist who cares. 
2. **Be Actionable**: Always clear about what needs to be done *today*.
3. **Be Safe**: Precise with dosages (e.g., "1 ml per Litre"). If a situation is critical, advise immediate local help.

## Formatting
- Respond in the EXACT same language/script the user used.
- Keep it under 250 words.
- Use bullet points for steps.
- **NO HEADERS**: Instead of "## Actionable Steps", just use "**What you should do today:**".
"""

def _get_crop_grounding_context(crop: str) -> str:
    """
    Compiles a comprehensive 'Crop Dossier' for the LLM.
    Aggregates fertilizers, irrigation, sowing, and pests for the detected crop.
    """
    if not crop:
        return ""

    crop_lower = crop.lower().strip()
    crop_profile = []
    
    # 1. Nutrient Info
    nutrients = FARMING_KNOWLEDGE.get("fertilizer", {}).get(crop_lower)
    if nutrients:
        crop_profile.append(f"**Nutrient & Fertilizer Support for {crop_lower.capitalize()}**")
        crop_profile.append(str(nutrients))

    # 2. Irrigation Info
    irrigation = FARMING_KNOWLEDGE.get("irrigation", {}).get(crop_lower)
    if irrigation:
        crop_profile.append(f"**Irrigation Schedule for {crop_lower.capitalize()}**")
        crop_profile.append(str(irrigation))

    # 3. Calendar & Tasks
    calendar = CROP_CALENDAR.get(crop_lower, {})
    if calendar:
        crop_profile.append(f"**Crop Lifecycle Calendar ({crop_lower.capitalize()})**")
        for season, tasks in calendar.items():
            crop_profile.append(f"*Season: {season.capitalize()}*")
            for t in tasks:
                crop_profile.append(f"- Week {t['week']}: {t['task']} | Priority: {t['priority']}")

    # 5. Market Info
    market = FARMING_KNOWLEDGE.get("market_info", {}).get(crop_lower)
    if market:
        crop_profile.append(f"**Market & MSP Info for {crop_lower.capitalize()}**")
        crop_profile.append(str(market))

    return "\n\n".join(crop_profile)



async def _call_nvidia(
    user_message: str,
    kb_context: str,
    history: list[dict[str, str]],
    language: str = "en",
) -> str | None:
    """Call NVIDIA NIM with grounding context. Returns None on any failure."""
    if not _NVIDIA_AVAILABLE or not _NVIDIA_API_KEY:
        return None

    try:
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        
        # Add history
        for msg in history[:-1]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Build prompt
        lang_hint = f"Respond in {'Hindi' if language == 'hi' else language}." if language != "en" else ""
        context_block = f"[CONTEXT from Annadata knowledge base]\n{kb_context}\n[/CONTEXT]\n\n" if kb_context else ""
        user_prompt = f"{lang_hint}\n\n{context_block}Farmer's question: {user_message}"
        
        messages.append({"role": "user", "content": user_prompt})

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_NVIDIA_ENDPOINT}/chat/completions",
                headers={
                    "Authorization": f"Bearer {_NVIDIA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _NVIDIA_MODEL,
                    "messages": messages,
                    "temperature": 0.5,
                    "top_p": 0.7,
                    "max_tokens": 1024,
                },
            )
            
            if response.status_code != 200:
                logger.error(f"NVIDIA API Error: {response.status_code} - {response.text}")
                return None
                
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
            
    except Exception:
        logger.exception("NVIDIA NIM call failed — falling back to rule-based.")
        return None


# ============================================================
# Knowledge Base
# ============================================================

FARMING_KNOWLEDGE: dict[str, dict[str, Any]] = {
    "fertilizer": {
        "wheat": {
            "urea": "120 kg/ha — apply 60 kg at sowing and 60 kg at first irrigation (CRI stage, 21 DAS)",
            "dap": "60 kg/ha at sowing as basal dose; provides 27 kg N + 30 kg P₂O₅",
            "mop": "40 kg/ha at sowing for potassium on deficient soils",
            "zinc_sulphate": "25 kg/ha at sowing if Zn < 0.6 ppm in soil",
            "total_npk": "120:60:40 kg NPK/ha recommended for irrigated timely-sown wheat",
            "schedule": [
                "At sowing: full P, full K, half N (60 kg urea + 60 kg DAP + 40 kg MOP)",
                "At CRI (21 DAS): remaining half N (60 kg urea) with first irrigation",
                "Foliar ZnSO₄ 0.5% spray at tillering if deficiency symptoms appear",
            ],
        },
        "rice": {
            "urea": "130 kg/ha — split into 3 doses: 1/3 basal, 1/3 at tillering, 1/3 at panicle initiation",
            "dap": "65 kg/ha as basal dose at transplanting",
            "mop": "50 kg/ha — half basal, half at panicle initiation",
            "zinc_sulphate": "25 kg/ha at last puddling for zinc-deficient soils",
            "total_npk": "120:60:60 kg NPK/ha recommended for irrigated transplanted rice",
            "schedule": [
                "Basal (at transplanting): 1/3 N + full P + half K (43 kg urea + 65 kg DAP + 25 kg MOP)",
                "At tillering (21 DAT): 1/3 N (43 kg urea)",
                "At panicle initiation (45 DAT): 1/3 N + remaining K (43 kg urea + 25 kg MOP)",
            ],
        },
        "maize": {
            "urea": "175 kg/ha — split: 1/3 basal, 1/3 at knee-high, 1/3 at tasseling",
            "dap": "75 kg/ha as basal dose",
            "mop": "50 kg/ha at sowing",
            "total_npk": "150:60:60 kg NPK/ha for hybrid irrigated maize",
            "schedule": [
                "At sowing: 1/3 N + full P + full K",
                "At knee-high (30 DAS): 1/3 N with earthing up",
                "At tasseling (50 DAS): remaining 1/3 N",
            ],
        },
        "sugarcane": {
            "urea": "350 kg/ha — split into 3 equal doses at 30, 60, and 90 days after planting",
            "dap": "85 kg/ha at planting in furrows",
            "mop": "80 kg/ha at planting",
            "total_npk": "250:60:60 kg NPK/ha for plant crop",
            "schedule": [
                "At planting: full P + full K in furrows",
                "30 DAP: 1/3 N (115 kg urea) with first earthing up",
                "60 DAP: 1/3 N (115 kg urea) with second earthing up",
                "90 DAP: 1/3 N (120 kg urea) with final earthing up",
            ],
        },
        "mustard": {
            "urea": "85 kg/ha — half at sowing, half at first irrigation",
            "dap": "50 kg/ha at sowing",
            "sulphur": "20 kg S/ha through gypsum or SSP",
            "total_npk": "80:40:0 kg NPK/ha with 20 kg S/ha",
            "schedule": [
                "At sowing: half N + full P + sulphur",
                "At first irrigation (25–30 DAS): remaining half N",
            ],
        },
        "cotton": {
            "urea": "200 kg/ha — split into 4 equal doses",
            "dap": "60 kg/ha at sowing",
            "mop": "50 kg/ha — half basal, half at squaring",
            "total_npk": "150:60:60 kg NPK/ha for irrigated Bt cotton",
            "schedule": [
                "At sowing: 1/4 N + full P + half K",
                "At squaring (40 DAS): 1/4 N + remaining K",
                "At flowering (65 DAS): 1/4 N",
                "At boll formation (85 DAS): 1/4 N",
            ],
        },
        "potato": {
            "urea": "170 kg/ha — 2/3 at planting, 1/3 at earthing up (30 DAP)",
            "dap": "125 kg/ha at planting",
            "mop": "100 kg/ha at planting",
            "total_npk": "150:80:100 kg NPK/ha for irrigated potato",
            "schedule": [
                "At planting: 2/3 N + full P + full K in furrows",
                "At earthing up (30 DAP): remaining 1/3 N",
            ],
        },
    },
    "irrigation": {
        "wheat": {
            "total": "5–6 irrigations of 6 cm depth each",
            "critical_stages": "Crown Root Initiation (CRI, 21 DAS), tillering, jointing, flowering, milk/dough stage",
            "schedule": [
                {
                    "stage": "CRI (21 DAS)",
                    "priority": "critical",
                    "note": "Most critical; skipping causes 30–40% yield loss",
                },
                {
                    "stage": "Tillering (40-45 DAS)",
                    "priority": "high",
                    "note": "Promotes tiller survival",
                },
                {
                    "stage": "Jointing (60-65 DAS)",
                    "priority": "high",
                    "note": "Determines spike length",
                },
                {
                    "stage": "Flowering (80-85 DAS)",
                    "priority": "critical",
                    "note": "Critical for grain set",
                },
                {
                    "stage": "Milk stage (95-100 DAS)",
                    "priority": "medium",
                    "note": "For grain filling",
                },
                {
                    "stage": "Dough stage (110-115 DAS)",
                    "priority": "low",
                    "note": "Light irrigation if dry spell",
                },
            ],
            "note": "If only 1 irrigation possible, irrigate at CRI. If 2, irrigate at CRI + flowering.",
        },
        "rice": {
            "total": "Continuous submergence with intermittent drying during vegetative phase saves 20-25% water",
            "critical_stages": "Transplanting, tillering, panicle initiation, flowering, grain filling",
            "schedule": [
                {
                    "stage": "Transplanting to tillering",
                    "priority": "critical",
                    "note": "Maintain 2–5 cm standing water",
                },
                {
                    "stage": "Mid-tillering",
                    "priority": "medium",
                    "note": "Drain for 2–3 days to control unproductive tillers",
                },
                {
                    "stage": "Panicle initiation",
                    "priority": "critical",
                    "note": "Maintain 5 cm standing water",
                },
                {
                    "stage": "Flowering",
                    "priority": "critical",
                    "note": "Water stress causes sterility; maintain 5 cm",
                },
                {
                    "stage": "Grain filling to maturity",
                    "priority": "high",
                    "note": "Gradually reduce; drain 15 days before harvest",
                },
            ],
            "note": "Alternate wetting and drying (AWD) technique can save 20–25% irrigation water.",
        },
        "maize": {
            "total": "6–8 irrigations depending on season and soil type",
            "critical_stages": "Knee-high, tasseling, silking, grain filling",
            "schedule": [
                {
                    "stage": "Knee-high (25–30 DAS)",
                    "priority": "high",
                    "note": "Promotes root development",
                },
                {
                    "stage": "Tasseling (50 DAS)",
                    "priority": "critical",
                    "note": "Most critical; 2–3 day stress reduces yield 20%",
                },
                {
                    "stage": "Silking (55-60 DAS)",
                    "priority": "critical",
                    "note": "Required for pollination and grain set",
                },
                {
                    "stage": "Grain filling (75-85 DAS)",
                    "priority": "high",
                    "note": "For proper kernel development",
                },
            ],
            "note": "Avoid waterlogging — maize is very sensitive to excess moisture.",
        },
        "sugarcane": {
            "total": "18–28 irrigations depending on soil and climate; 1500–2500 mm total water",
            "critical_stages": "Germination, tillering, grand growth, maturity",
            "schedule": [
                {
                    "stage": "Germination (0–30 DAP)",
                    "priority": "critical",
                    "note": "Light frequent irrigation every 7 days",
                },
                {
                    "stage": "Tillering (30–120 DAP)",
                    "priority": "high",
                    "note": "Irrigate every 10–15 days",
                },
                {
                    "stage": "Grand growth (120–270 DAP)",
                    "priority": "critical",
                    "note": "Maximum water need; irrigate every 7–10 days",
                },
                {
                    "stage": "Maturity (270+ DAP)",
                    "priority": "low",
                    "note": "Withhold irrigation 15–20 days before harvest",
                },
            ],
            "note": "Drip irrigation at 80% ET can save 30–40% water and increase yield by 20%.",
        },
        "mustard": {
            "total": "1–2 irrigations; mustard is drought-tolerant",
            "critical_stages": "Pre-flowering (40–45 DAS), pod filling (70–75 DAS)",
            "schedule": [
                {
                    "stage": "Pre-flowering (40-45 DAS)",
                    "priority": "critical",
                    "note": "Only critical irrigation",
                },
                {
                    "stage": "Pod filling (70-75 DAS)",
                    "priority": "medium",
                    "note": "If soil is very dry",
                },
            ],
            "note": "Excess irrigation promotes vegetative growth and aphid infestation. Avoid waterlogging.",
        },
        "cotton": {
            "total": "6–8 irrigations depending on monsoon and soil type",
            "critical_stages": "Squaring, flowering, boll development",
            "schedule": [
                {
                    "stage": "First irrigation (20–25 DAS)",
                    "priority": "high",
                    "note": "For root establishment",
                },
                {
                    "stage": "Squaring (40 DAS)",
                    "priority": "critical",
                    "note": "Promotes flower bud development",
                },
                {
                    "stage": "Flowering (60-80 DAS)",
                    "priority": "critical",
                    "note": "Most sensitive period",
                },
                {
                    "stage": "Boll development (80-120 DAS)",
                    "priority": "high",
                    "note": "For boll weight and fiber quality",
                },
            ],
            "note": "Drip irrigation with fertigation increases yield by 25–30% and saves 40% water.",
        },
        "potato": {
            "total": "8–12 irrigations at 7–10 day intervals",
            "critical_stages": "Stolon formation, tuber initiation, tuber bulking",
            "schedule": [
                {
                    "stage": "After planting (3–4 DAP)",
                    "priority": "high",
                    "note": "Light irrigation for germination",
                },
                {
                    "stage": "Stolon formation (25-30 DAP)",
                    "priority": "critical",
                    "note": "Determines number of tubers",
                },
                {
                    "stage": "Tuber initiation (35-45 DAP)",
                    "priority": "critical",
                    "note": "Moisture stress causes misshapen tubers",
                },
                {
                    "stage": "Tuber bulking (45-80 DAP)",
                    "priority": "critical",
                    "note": "Regular irrigation for uniform growth",
                },
                {
                    "stage": "Maturity (80-90 DAP)",
                    "priority": "low",
                    "note": "Reduce irrigation; stop 10 days before harvest",
                },
            ],
            "note": "Maintain soil moisture at 70–80% field capacity. Ridges help manage drainage.",
        },
    },
    "pest_management": {
        "wheat": {
            "yellow_rust": {
                "symptoms": "Yellow-orange powdery pustules in stripes on leaves",
                "conditions": "Cool (10–15°C), humid weather; appears in Jan–Feb in North India",
                "control": "Spray Propiconazole 25 EC @ 0.1% (1 ml/L) or Tebuconazole 250 EC @ 1 ml/L. Repeat after 15 days if needed.",
                "prevention": "Use resistant varieties (HD 3226, PBW 826). Early sowing reduces risk.",
            },
            "brown_rust": {
                "symptoms": "Small, round, orange-brown pustules scattered on leaves",
                "conditions": "Moderate temperatures (15–25°C) with high humidity",
                "control": "Same as yellow rust — spray Propiconazole @ 0.1%",
                "prevention": "Resistant varieties and timely sowing",
            },
            "aphids": {
                "symptoms": "Colonies of small green/black insects on leaves and ears; honeydew secretion",
                "conditions": "Warm, dry weather in Feb–Mar",
                "control": "Spray Imidacloprid 17.8 SL @ 0.5 ml/L or Thiamethoxam 25 WG @ 0.3 g/L",
                "prevention": "Avoid excess nitrogen. Use yellow sticky traps for early monitoring.",
            },
            "termites": {
                "symptoms": "Plants dry up in patches; roots hollowed out and filled with soil",
                "conditions": "Sandy and light-textured soils with low organic matter",
                "control": "Soil application of Chlorpyrifos 20 EC @ 5 L/ha with irrigation water",
                "prevention": "Use well-decomposed FYM. Treat seed with Chlorpyrifos @ 4 ml/kg.",
            },
        },
        "rice": {
            "stem_borer": {
                "symptoms": "Dead hearts in vegetative stage; white ears in reproductive stage",
                "conditions": "Warm, humid weather; staggered planting favors infestation",
                "control": "Apply Cartap hydrochloride 4G @ 25 kg/ha or spray Chlorantraniliprole 18.5 SC @ 0.3 ml/L",
                "prevention": "Remove stubbles after harvest. Clip seedling tips before transplanting. Use pheromone traps.",
            },
            "bph": {
                "symptoms": "Hopperburn — circular patches of dried plants in field",
                "conditions": "High humidity, dense canopy, excess nitrogen",
                "control": "Spray Pymetrozine 50 WG @ 0.6 g/L or Dinotefuran 20 SG @ 0.5 g/L at base of plants",
                "prevention": "Do not apply excess nitrogen. Drain field for 3–4 days. Avoid broad-spectrum insecticides.",
            },
            "blast": {
                "symptoms": "Diamond-shaped spots on leaves with grey center; neck blast causes broken panicle",
                "conditions": "Cool nights (20–26°C), high humidity, excess nitrogen",
                "control": "Spray Tricyclazole 75 WP @ 0.6 g/L or Isoprothiolane 40 EC @ 1.5 ml/L",
                "prevention": "Use resistant varieties (Pusa Basmati 1847). Balanced fertilization.",
            },
            "sheath_blight": {
                "symptoms": "Oval, greenish-grey lesions on leaf sheath near water line",
                "conditions": "High plant density, high nitrogen, warm humid weather",
                "control": "Spray Hexaconazole 5 EC @ 2 ml/L or Validamycin 3 L @ 2.5 ml/L",
                "prevention": "Avoid excessive close spacing. Balanced N application.",
            },
        },
        "cotton": {
            "bollworm": {
                "symptoms": "Bore holes in bolls with frass; damaged bolls rot or produce low quality lint",
                "conditions": "Warm humid weather; non-Bt cotton highly susceptible",
                "control": "Spray Emamectin benzoate 5 SG @ 0.4 g/L or Chlorantraniliprole @ 0.3 ml/L",
                "prevention": "Plant Bt cotton hybrids. Maintain 20% non-Bt refuge. Use pheromone traps.",
            },
            "whitefly": {
                "symptoms": "Sooty mould on leaves; sticky honeydew; cotton leaf curl virus transmission",
                "conditions": "Hot, dry weather; July–September peak",
                "control": "Spray Diafenthiuron 50 WP @ 1 g/L or Pyriproxyfen 10 EC @ 1 ml/L",
                "prevention": "Remove alternate host weeds. Avoid excess N. Use yellow sticky traps.",
            },
        },
        "maize": {
            "fall_armyworm": {
                "symptoms": "Irregular holes in leaves; large caterpillars with inverted Y-mark on head",
                "conditions": "Warm humid conditions; year-round in peninsular India",
                "control": "Spray Spinetoram 11.7 SC @ 0.5 ml/L or Emamectin benzoate 5 SG @ 0.4 g/L into whorl",
                "prevention": "Apply Trichogramma egg parasitoid cards (1 lakh eggs/ha). Scout weekly from emergence.",
            },
            "stem_borer": {
                "symptoms": "Shot holes on leaves; dead hearts; stems broken at node",
                "conditions": "Late-sown crops more susceptible",
                "control": "Apply Carbofuran 3G granules in whorl @ 8–10 kg/ha",
                "prevention": "Timely sowing. Destroy stubbles after harvest.",
            },
        },
        "potato": {
            "late_blight": {
                "symptoms": "Dark, water-soaked spots on leaves and stems; white fungal growth on underside",
                "conditions": "Cool (10–20°C), foggy, humid weather; Dec–Jan in North India",
                "control": "Spray Mancozeb 75 WP @ 2.5 g/L preventively. For curative, use Cymoxanil + Mancozeb @ 3 g/L.",
                "prevention": "Use resistant varieties (Kufri Badshah). Certified disease-free seed. Spray prophylactically.",
            },
            "aphids": {
                "symptoms": "Curling of leaves; transmission of potato viruses (PVY, PLRV)",
                "conditions": "Warm, dry weather; Feb–Mar",
                "control": "Spray Imidacloprid 17.8 SL @ 0.5 ml/L or Thiamethoxam 25 WG @ 0.3 g/L",
                "prevention": "Dehaulm (cut haulms) by end of January in seed crop areas.",
            },
        },
    },
    "sowing": {
        "wheat": {
            "rabi": {
                "optimal_date_range": "November 1 – November 25",
                "late_sowing_range": "November 25 – December 25 (increase seed rate by 25%)",
                "seed_rate": "100–125 kg/ha (timely); 125–150 kg/ha (late sown)",
                "seed_treatment": "Carboxin + Thiram (Vitavax Power) @ 2.5 g/kg seed for smut and root rot",
                "spacing": "Row-to-row: 20–22.5 cm; seed depth 4–5 cm",
                "soil_preparation": "2–3 deep ploughings + planking; pre-sowing irrigation (rauni/palewa) 3–4 days before",
                "varieties": {
                    "north_india": ["HD 3226", "PBW 826", "DBW 327", "WH 1270"],
                    "central_india": ["HI 1634", "MP 3336", "JW 3382"],
                    "peninsular": ["NI 5439", "NIAW 3170"],
                },
            },
        },
        "rice": {
            "kharif": {
                "optimal_date_range": "June 15 – July 15 (transplanting)",
                "nursery_sowing": "May 15 – June 15 (25-30 day old seedlings for transplanting)",
                "seed_rate": "20–25 kg/ha (transplanted); 30–40 kg/ha (direct seeded)",
                "seed_treatment": "Carbendazim 50 WP @ 2 g/kg seed for blast prevention",
                "spacing": "20 �- 15 cm (fine grain); 20 �- 20 cm (coarse grain)",
                "soil_preparation": "2 dry ploughings in summer, puddling in standing water; level field for uniform water",
                "varieties": {
                    "north_india": [
                        "Pusa Basmati 1847",
                        "PB 1509",
                        "PR 126",
                        "Pusa 44",
                    ],
                    "east_india": ["Swarna", "Rajendra Mahsuri", "Sahbhagi Dhan"],
                    "south_india": ["BPT 5204 (Samba Mahsuri)", "ADT 45", "CO 51"],
                },
            },
        },
        "maize": {
            "kharif": {
                "optimal_date_range": "June 15 – July 15",
                "seed_rate": "20–25 kg/ha for hybrids",
                "seed_treatment": "Thiram @ 3 g/kg seed",
                "spacing": "60 �- 20 cm (30,000–35,000 plants/ha)",
                "varieties": {
                    "north_india": ["PMH 1", "HQPM 1", "DHM 121"],
                    "peninsular": ["NK 6240", "DKC 9164", "900M Gold"],
                },
            },
            "rabi": {
                "optimal_date_range": "October 15 – November 15",
                "seed_rate": "20 kg/ha",
                "spacing": "60 �- 20 cm",
                "note": "Winter maize grown mainly in Bihar, West Bengal, and peninsular India",
            },
        },
        "mustard": {
            "rabi": {
                "optimal_date_range": "October 5 – October 25",
                "seed_rate": "3–5 kg/ha",
                "seed_treatment": "Metalaxyl 35 SD @ 6 g/kg seed for white rust",
                "spacing": "30 �- 10 cm (row �- plant); 45 �- 15 cm for irrigated",
                "varieties": {
                    "north_india": ["Pusa Bold", "RH 749", "NRCHB 101"],
                    "rajasthan": ["RH 725", "Pusa Tarak", "NRCDR 2"],
                },
            },
        },
        "potato": {
            "rabi": {
                "optimal_date_range": "October 15 – November 10 (plains); March – April (hills)",
                "seed_rate": "20–25 quintals/ha (25–50 g tubers)",
                "seed_treatment": "Dip in Mancozeb 0.25% solution for 10 min; shade dry before planting",
                "spacing": "60 �- 20 cm on ridges; 4–5 cm depth",
                "varieties": {
                    "north_india": ["Kufri Pukhraj", "Kufri Badshah", "Kufri Jyoti"],
                    "processing": ["Kufri Chipsona 1", "Kufri Chipsona 3", "Atlantic"],
                },
            },
        },
        "cotton": {
            "kharif": {
                "optimal_date_range": "April 15 – May 15 (irrigated); June with onset of monsoon (rainfed)",
                "seed_rate": "2.5 kg/ha (Bt hybrids, 450 g packets for 1 acre)",
                "spacing": "90–100 �- 60–90 cm for Bt hybrids",
                "varieties": {
                    "north_india": ["RCH 773 BGII", "MRC 7361 BGII", "Ankur 3244 BGII"],
                    "central_india": ["Ajeet 199", "Jadoo BGII"],
                    "note": "Always maintain 20% non-Bt refuge (5 rows of non-Bt for every 20 rows of Bt)",
                },
            },
        },
        "sugarcane": {
            "spring": {
                "optimal_date_range": "February 15 – March 15",
                "seed_rate": "40,000–45,000 three-budded setts/ha (75–80 quintals/ha)",
                "seed_treatment": "Dip setts in Carbendazim 0.1% + Malathion 0.1% for 10 min",
                "spacing": "75–90 cm row-to-row; setts placed end-to-end in furrows",
                "varieties": {
                    "north_india": ["CoS 767", "Co 0238", "CoLk 94184", "CoPk 05191"],
                    "peninsular": ["Co 86032", "CoC 671", "CoM 0265"],
                },
            },
            "autumn": {
                "optimal_date_range": "October 1 – October 31",
                "seed_rate": "Same as spring planting",
                "note": "Autumn planting gives 15–20% higher yield than spring; mainly in subtropical India.",
            },
        },
    },
    "harvest": {
        "wheat": {
            "timing": "Grain moisture content 12–14%; golden yellow colour; grain hard when pressed",
            "duration": "135–150 days after sowing (mid-March to mid-April in North India)",
            "method": "Combine harvester preferred; manual harvesting 3–5 cm above ground",
            "post_harvest": "Thresh within 3–4 days of cutting. Sun-dry to 12% moisture for safe storage.",
            "yield": "40–55 quintals/ha (irrigated, timely sown); 25–35 quintals/ha (late sown)",
        },
        "rice": {
            "timing": "80% grains in panicle are golden yellow; moisture 20–22% at harvest",
            "duration": "120–150 days after transplanting (October–November for kharif)",
            "method": "Combine harvester or manual harvesting; drain field 10–15 days before",
            "post_harvest": "Dry paddy to 14% moisture. Avoid drying on road — causes grain breakage.",
            "yield": "45–60 quintals/ha (irrigated hybrid); 30–40 quintals/ha (traditional)",
        },
        "maize": {
            "timing": "Husk turns brown and dry; black layer visible at base of kernel",
            "duration": "90–110 days after sowing",
            "method": "Cobs picked by hand; kernels separated after drying",
            "post_harvest": "Dry kernels to 12% moisture. Store in airtight containers to prevent aflatoxin.",
            "yield": "60–80 quintals/ha (hybrid irrigated); 25–40 quintals/ha (rainfed)",
        },
        "sugarcane": {
            "timing": "Brix value > 20% on hand refractometer; 10–12 months after planting",
            "duration": "February – April (spring planted); December – February (autumn planted)",
            "method": "Cut at ground level with sharp billhook; remove green tops",
            "post_harvest": "Crush within 24–48 hours of harvest for maximum sugar recovery.",
            "yield": "700–1000 quintals/ha (plant crop); 600–800 quintals/ha (ratoon)",
        },
        "mustard": {
            "timing": "Pods turn yellowish-brown; seeds become brown and hard",
            "duration": "120–140 days after sowing (February–March)",
            "method": "Harvest in morning hours to prevent shattering; dry in shade for 4–5 days",
            "post_harvest": "Thresh with sticks. Clean and dry to 8% moisture for safe storage.",
            "yield": "15–20 quintals/ha (irrigated); 8–12 quintals/ha (rainfed)",
        },
        "cotton": {
            "timing": "Bolls burst open and lint is fluffy white",
            "duration": "150–180 days; 3–4 pickings at 15-day intervals from September onwards",
            "method": "Hand-pick only fully opened bolls in dry conditions. Avoid mixing with trash.",
            "post_harvest": "Sun-dry picked cotton to reduce moisture. Grade before selling.",
            "yield": "20–25 quintals seed cotton/ha (Bt irrigated); 10–15 quintals/ha (rainfed)",
        },
        "potato": {
            "timing": "Haulms turn yellow and dry; skin of tuber doesn't peel off easily",
            "duration": "75–100 days after planting (January–February in plains)",
            "method": "Cut haulms 10 days before digging. Use potato digger or spade carefully.",
            "post_harvest": "Cure at 15–20°C for 10 days. Cold store at 2–4°C for table purpose, 10–12°C for processing.",
            "yield": "250–350 quintals/ha",
        },
    },
    "market_info": {
        "wheat": {
            "msp_2025_26": "Rs 2,425 per quintal",
            "procurement": "FCI and state agencies at MSP during April–June",
            "tips": "Register on e-NAM (National Agriculture Market) for better price discovery.",
        },
        "rice": {
            "msp_2025_26": "Rs 2,300 per quintal (Common); Rs 2,320 per quintal (Grade A)",
            "procurement": "Government procurement during October–January",
            "tips": "Paddy should have max 17% moisture for procurement. Grade A fetches premium.",
        },
        "maize": {
            "msp_2025_26": "Rs 2,090 per quintal",
            "procurement": "State agencies in select states; limited government procurement",
            "tips": "Poultry feed industry is a major buyer; contract farming can ensure better prices.",
        },
        "sugarcane": {
            "frp_2025_26": "Rs 340 per quintal (at 10.25% basic recovery rate)",
            "sap_note": "State Advised Price (SAP) varies: UP Rs 380/qtl, Haryana Rs 400/qtl (approx.)",
            "tips": "Higher sugar recovery in your cane means premium; maintain quality for bonus.",
        },
        "mustard": {
            "msp_2025_26": "Rs 5,950 per quintal",
            "procurement": "NAFED as central agency; limited procurement in Rajasthan, MP, Haryana",
            "tips": "Clean, well-dried mustard with low moisture fetches better rates at mandis.",
        },
        "cotton": {
            "msp_2025_26": "Rs 7,521 per quintal (medium staple); Rs 7,921 per quintal (long staple)",
            "procurement": "CCI as central agency; state cooperatives",
            "tips": "Staple length and trash content determine grade and price. Pick clean.",
        },
        "potato": {
            "note": "No MSP for potato; market-driven pricing",
            "average_price": "Rs 800–1,500 per quintal depending on season and supply",
            "tips": "Store in cold storage for off-season sale at premium. Contract farming with chip companies.",
        },
    },
}

GOVERNMENT_SCHEMES: list[dict[str, Any]] = [
    {
        "id": "pm-kisan",
        "name": "PM-KISAN Samman Nidhi",
        "description": "Direct income support of Rs 6,000 per year to all landholding farmer families across the country.",
        "benefit": "Rs 6,000/year in 3 installments of Rs 2,000 each",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": "Institutional landholders, income tax payers, government servants, pensioners (>Rs 10,000/month)",
        },
        "application_url": "https://pmkisan.gov.in",
        "documents_required": [
            "Aadhaar card",
            "Bank account (Aadhaar-linked)",
            "Land records",
        ],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "income_support",
    },
    {
        "id": "pmfby",
        "name": "Pradhan Mantri Fasal Bima Yojana",
        "description": "Comprehensive crop insurance scheme providing financial support to farmers in case of crop loss due to natural calamities, pests, and diseases.",
        "benefit": "Crop insurance at subsidized premium — 2% for kharif, 1.5% for rabi, 5% for commercial/horticultural crops",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "https://pmfby.gov.in",
        "documents_required": [
            "Aadhaar card",
            "Bank account",
            "Land records / Tenancy agreement",
            "Sowing certificate",
        ],
        "applicable_states": "all",
        "crop_specific": True,
        "category": "insurance",
    },
    {
        "id": "soil-health-card",
        "name": "Soil Health Card Scheme",
        "description": "Government provides soil health cards to farmers with crop-wise nutrient recommendations based on soil testing.",
        "benefit": "Free soil testing and customized fertilizer recommendation every 2 years",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "https://soilhealth.dac.gov.in",
        "documents_required": ["Aadhaar card", "Land details"],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "soil_health",
    },
    {
        "id": "kcc",
        "name": "Kisan Credit Card",
        "description": "Provides short-term credit to farmers for crop production, post-harvest, and maintenance of farm assets at subsidized 4% interest rate.",
        "benefit": "Credit limit up to Rs 3 lakh at 4% interest (with prompt repayment subvention); Rs 1.6 lakh without collateral",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "Apply at any commercial/cooperative/regional rural bank",
        "documents_required": [
            "Aadhaar card",
            "PAN card",
            "Land records",
            "Passport photo",
            "Bank application form",
        ],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "credit",
    },
    {
        "id": "pm-kusum",
        "name": "PM-KUSUM (Kisan Urja Suraksha evam Utthaan Mahabhiyan)",
        "description": "Promotes solar energy in agriculture: solar pumps, grid-connected solar plants, and solarization of existing pumps.",
        "benefit": "60% subsidy on solar pumps (30% central + 30% state); up to 7.5 HP solar pump; extra income from surplus solar power",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "https://pmkusum.mnre.gov.in",
        "documents_required": [
            "Aadhaar card",
            "Land records",
            "Bank account",
            "Electricity connection details (if solarizing)",
        ],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "infrastructure",
    },
    {
        "id": "pkvy",
        "name": "Paramparagat Krishi Vikas Yojana (PKVY)",
        "description": "Promotes organic farming through cluster approach with financial assistance for conversion to organic.",
        "benefit": "Rs 50,000/ha over 3 years (Rs 31,000 to farmer for inputs, Rs 8,800 for value addition and marketing)",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": "Must form cluster of 20+ hectares with 50+ farmers",
        },
        "application_url": "Apply through District Agriculture Office or https://pgsindia-ncof.gov.in",
        "documents_required": [
            "Aadhaar card",
            "Land records",
            "Cluster formation documents",
        ],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "organic_farming",
    },
    {
        "id": "nmsa",
        "name": "National Mission for Sustainable Agriculture (NMSA)",
        "description": "Promotes sustainable agriculture through soil health management, rainfed area development, and climate change adaptation.",
        "benefit": "50% subsidy on micro-irrigation (drip/sprinkler); assistance for water harvesting structures",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "Apply through District Agriculture Office",
        "documents_required": ["Aadhaar card", "Land records", "Bank account"],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "sustainability",
    },
    {
        "id": "smam",
        "name": "Sub-Mission on Agricultural Mechanization (SMAM)",
        "description": "Provides subsidies for purchase of agricultural machinery and equipment and establishment of custom hiring centres.",
        "benefit": "40–50% subsidy on farm machinery for small/marginal farmers; 25–40% for others",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "https://agrimachinery.nic.in",
        "documents_required": [
            "Aadhaar card",
            "Land records",
            "Bank account",
            "Caste certificate (if SC/ST)",
        ],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "mechanization",
    },
    {
        "id": "rkvy",
        "name": "Rashtriya Krishi Vikas Yojana (RKVY-RAFTAAR)",
        "description": "Supports state-specific agricultural development projects including agri-infrastructure, value addition, and agri-entrepreneurship.",
        "benefit": "Varies by project — grants for agri-startups (up to Rs 25 lakh), infrastructure projects funded up to 100%",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "https://rkvy.nic.in",
        "documents_required": ["Varies by state and project type"],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "agri_startup",
    },
    {
        "id": "enam",
        "name": "e-NAM (National Agriculture Market)",
        "description": "Online trading platform for agricultural commodities connecting APMC mandis across states for transparent price discovery.",
        "benefit": "Access to buyers across India; transparent bidding; direct payment to bank account; reduced intermediary costs",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "https://enam.gov.in",
        "documents_required": [
            "Aadhaar card",
            "Bank account",
            "Mandi license (or apply through FPO)",
        ],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "market_access",
    },
    {
        "id": "pmksy",
        "name": "Pradhan Mantri Krishi Sinchayee Yojana (PMKSY)",
        "description": "Ensures access to irrigation ('Har Khet Ko Paani') and promotes micro-irrigation ('Per Drop More Crop').",
        "benefit": "55% subsidy on micro-irrigation for small/marginal farmers (45% for others); support for water harvesting",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "Apply through District Agriculture/Horticulture Office or https://pmksy.gov.in",
        "documents_required": [
            "Aadhaar card",
            "Land records",
            "Bank account",
            "Quotation from drip/sprinkler supplier",
        ],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "irrigation",
    },
    {
        "id": "agri-infra-fund",
        "name": "Agriculture Infrastructure Fund (AIF)",
        "description": "Rs 1 lakh crore financing facility for post-harvest management and community farming assets.",
        "benefit": "3% interest subvention on loans up to Rs 2 crore; credit guarantee under CGTMSE",
        "eligibility": {
            "land_holding_max_ha": None,
            "category": ["small_marginal", "medium", "large"],
            "exclusions": None,
        },
        "application_url": "https://agriinfra.dac.gov.in",
        "documents_required": [
            "Project report",
            "Aadhaar card",
            "Bank account",
            "Land/rental documents",
        ],
        "applicable_states": "all",
        "crop_specific": False,
        "category": "infrastructure",
    },
]

CROP_CALENDAR: dict[str, dict[str, list[dict[str, Any]]]] = {
    "wheat": {
        "rabi": [
            {
                "week": 1,
                "month": "October",
                "start_day": 15,
                "task": "Field preparation — 2-3 deep ploughings followed by planking to level field",
                "details": "Incorporate 10-12 tonnes FYM/ha during last ploughing. Get soil tested.",
                "priority": "high",
            },
            {
                "week": 2,
                "month": "October",
                "start_day": 22,
                "task": "Pre-sowing irrigation (rauni/palewa)",
                "details": "Give a heavy irrigation 3-4 days before sowing for optimum moisture at sowing.",
                "priority": "high",
            },
            {
                "week": 3,
                "month": "November",
                "start_day": 1,
                "task": "Sowing with basal fertilizer application",
                "details": "Sow at 100-125 kg/ha seed rate with full DAP + MOP + half urea as basal. Row spacing 20-22.5 cm.",
                "priority": "critical",
            },
            {
                "week": 4,
                "month": "November",
                "start_day": 15,
                "task": "Herbicide application (if needed)",
                "details": "Spray Sulfosulfuron 75 WG @ 25 g/ha or Clodinafop + Metsulfuron at 21-25 DAS for weeds.",
                "priority": "medium",
            },
            {
                "week": 5,
                "month": "November",
                "start_day": 22,
                "task": "First irrigation at Crown Root Initiation (CRI)",
                "details": "Most critical irrigation at 21 DAS. Apply remaining half urea (60 kg/ha) with this irrigation.",
                "priority": "critical",
            },
            {
                "week": 6,
                "month": "December",
                "start_day": 10,
                "task": "Second irrigation at tillering",
                "details": "Irrigate at 40-45 DAS. Scout for aphids and yellow rust symptoms.",
                "priority": "high",
            },
            {
                "week": 7,
                "month": "January",
                "start_day": 1,
                "task": "Third irrigation at jointing + field scouting",
                "details": "Irrigate at 60-65 DAS. Watch for yellow rust (orange stripes on leaves).",
                "priority": "high",
            },
            {
                "week": 8,
                "month": "January",
                "start_day": 15,
                "task": "Disease management spray (if needed)",
                "details": "If rust observed, spray Propiconazole 25 EC @ 1 ml/L. Repeat after 15 days if needed.",
                "priority": "medium",
            },
            {
                "week": 9,
                "month": "February",
                "start_day": 1,
                "task": "Fourth irrigation at flowering",
                "details": "Critical for grain set. Spray Imidacloprid if aphid colonies visible on ears.",
                "priority": "critical",
            },
            {
                "week": 10,
                "month": "February",
                "start_day": 15,
                "task": "Fifth irrigation at milk stage",
                "details": "Important for grain filling. Avoid water stress.",
                "priority": "high",
            },
            {
                "week": 11,
                "month": "March",
                "start_day": 1,
                "task": "Sixth irrigation at dough stage (if needed)",
                "details": "Light irrigation if hot winds prevail. No more irrigation after this.",
                "priority": "medium",
            },
            {
                "week": 12,
                "month": "March",
                "start_day": 20,
                "task": "Arrange for harvesting",
                "details": "Book combine harvester. Harvest when grain is hard, golden yellow, 12-14% moisture.",
                "priority": "high",
            },
            {
                "week": 13,
                "month": "April",
                "start_day": 1,
                "task": "Harvesting, threshing, and storage",
                "details": "Harvest, thresh within 3-4 days. Sun-dry to 12% moisture. Store in clean, dry godowns.",
                "priority": "critical",
            },
        ],
    },
    "rice": {
        "kharif": [
            {
                "week": 1,
                "month": "May",
                "start_day": 15,
                "task": "Nursery preparation and seed sowing",
                "details": "Prepare raised nursery beds. Sow pre-germinated seeds at 20-25 kg/ha. Keep moist.",
                "priority": "high",
            },
            {
                "week": 2,
                "month": "June",
                "start_day": 1,
                "task": "Main field preparation — ploughing and puddling",
                "details": "2 dry ploughings + 2-3 puddlings in standing water. Apply FYM @ 10 t/ha. Level field.",
                "priority": "high",
            },
            {
                "week": 3,
                "month": "June",
                "start_day": 15,
                "task": "Transplanting with basal fertilizer",
                "details": "Transplant 25-30 day old seedlings at 20x15 cm. Apply full DAP + half MOP as basal.",
                "priority": "critical",
            },
            {
                "week": 4,
                "month": "July",
                "start_day": 1,
                "task": "Gap filling and weed management",
                "details": "Fill gaps within 7-10 days. Apply Bispyribac Na @ 25 g/ha for weed control.",
                "priority": "high",
            },
            {
                "week": 5,
                "month": "July",
                "start_day": 7,
                "task": "First top-dressing of nitrogen",
                "details": "Apply 1/3 urea (43 kg/ha) at 21 DAT during tillering. Maintain 2-5 cm standing water.",
                "priority": "critical",
            },
            {
                "week": 6,
                "month": "July",
                "start_day": 21,
                "task": "Field scouting for stem borer, BPH",
                "details": "Check for dead hearts. Install pheromone traps. Drain field for 2-3 days to control tillers.",
                "priority": "medium",
            },
            {
                "week": 7,
                "month": "August",
                "start_day": 1,
                "task": "Second top-dressing at panicle initiation",
                "details": "Apply 1/3 urea + remaining MOP at 45 DAT. Maintain 5 cm standing water.",
                "priority": "critical",
            },
            {
                "week": 8,
                "month": "August",
                "start_day": 15,
                "task": "Pest and disease management",
                "details": "Spray for blast if symptoms appear (Tricyclazole @ 0.6 g/L). Check for BPH at base.",
                "priority": "high",
            },
            {
                "week": 9,
                "month": "September",
                "start_day": 1,
                "task": "Flowering stage care",
                "details": "Maintain 5 cm water. Do not spray insecticides during flowering to protect pollinators.",
                "priority": "high",
            },
            {
                "week": 10,
                "month": "September",
                "start_day": 15,
                "task": "Grain filling — maintain water and scout",
                "details": "Monitor for neck blast and sheath blight. Gradually reduce water.",
                "priority": "medium",
            },
            {
                "week": 11,
                "month": "October",
                "start_day": 1,
                "task": "Drain field before harvest",
                "details": "Stop irrigation 15 days before expected harvest. Field should be dry at harvest.",
                "priority": "high",
            },
            {
                "week": 12,
                "month": "October",
                "start_day": 15,
                "task": "Harvesting and post-harvest",
                "details": "Harvest when 80% grains are golden. Dry to 14% moisture. Do not burn stubble.",
                "priority": "critical",
            },
        ],
    },
    "maize": {
        "kharif": [
            {
                "week": 1,
                "month": "June",
                "start_day": 1,
                "task": "Field preparation",
                "details": "2-3 ploughings. Apply 10 t/ha FYM. Prepare ridges and furrows at 60 cm spacing.",
                "priority": "high",
            },
            {
                "week": 2,
                "month": "June",
                "start_day": 15,
                "task": "Sowing with basal fertilizer",
                "details": "Sow at 60x20 cm. Apply 1/3 N + full P + full K as basal. Treat seed with Thiram.",
                "priority": "critical",
            },
            {
                "week": 3,
                "month": "July",
                "start_day": 1,
                "task": "Thinning and gap filling",
                "details": "Maintain one plant per hill at 20 cm. Remove extra seedlings at 10-12 DAS.",
                "priority": "medium",
            },
            {
                "week": 4,
                "month": "July",
                "start_day": 15,
                "task": "First top-dressing + earthing up",
                "details": "Apply 1/3 N at knee-high (30 DAS). Earth up soil to base of plants for support.",
                "priority": "critical",
            },
            {
                "week": 5,
                "month": "July",
                "start_day": 25,
                "task": "Scout for fall armyworm",
                "details": "Check whorls for caterpillars. Apply Spinetoram if > 10% plants infested.",
                "priority": "high",
            },
            {
                "week": 6,
                "month": "August",
                "start_day": 5,
                "task": "Second top-dressing at tasseling",
                "details": "Apply remaining 1/3 N at 50 DAS. Irrigate if dry spell during tasseling-silking.",
                "priority": "critical",
            },
            {
                "week": 7,
                "month": "August",
                "start_day": 20,
                "task": "Irrigation at grain filling",
                "details": "Ensure moisture during grain filling. Avoid waterlogging.",
                "priority": "high",
            },
            {
                "week": 8,
                "month": "September",
                "start_day": 10,
                "task": "Harvest and post-harvest",
                "details": "Harvest when husk is brown and dry. Dry kernels to 12% moisture. Store airtight.",
                "priority": "critical",
            },
        ],
    },
    "mustard": {
        "rabi": [
            {
                "week": 1,
                "month": "September",
                "start_day": 25,
                "task": "Field preparation",
                "details": "2-3 ploughings to get fine tilth. Apply FYM @ 8-10 t/ha.",
                "priority": "high",
            },
            {
                "week": 2,
                "month": "October",
                "start_day": 10,
                "task": "Sowing with basal fertilizer",
                "details": "Sow at 3-5 kg/ha, 30x10 cm spacing. Apply half N + full P + sulphur as basal.",
                "priority": "critical",
            },
            {
                "week": 3,
                "month": "October",
                "start_day": 25,
                "task": "Thinning",
                "details": "Thin to one plant every 10-15 cm at 15-20 DAS.",
                "priority": "medium",
            },
            {
                "week": 4,
                "month": "November",
                "start_day": 10,
                "task": "First irrigation + top-dressing",
                "details": "Apply remaining N with first irrigation at 25-30 DAS.",
                "priority": "critical",
            },
            {
                "week": 5,
                "month": "December",
                "start_day": 1,
                "task": "Aphid monitoring",
                "details": "Check for mustard aphid on leaves and stems. Spray Imidacloprid if heavy infestation.",
                "priority": "high",
            },
            {
                "week": 6,
                "month": "December",
                "start_day": 15,
                "task": "White rust and Alternaria check",
                "details": "Spray Mancozeb @ 2.5 g/L if white pustules or dark spots seen on leaves.",
                "priority": "medium",
            },
            {
                "week": 7,
                "month": "January",
                "start_day": 5,
                "task": "Second irrigation at pod filling",
                "details": "Light irrigation at 70-75 DAS if soil is dry. Avoid excess water.",
                "priority": "medium",
            },
            {
                "week": 8,
                "month": "February",
                "start_day": 15,
                "task": "Harvesting",
                "details": "Harvest when 75% pods turn yellow-brown. Harvest in morning to prevent shattering. Dry in shade.",
                "priority": "critical",
            },
        ],
    },
    "cotton": {
        "kharif": [
            {
                "week": 1,
                "month": "April",
                "start_day": 1,
                "task": "Field preparation",
                "details": "Deep ploughing + 2-3 harrowings. Apply FYM @ 10 t/ha. Form ridges at 90-100 cm.",
                "priority": "high",
            },
            {
                "week": 2,
                "month": "April",
                "start_day": 20,
                "task": "Sowing",
                "details": "Dibble Bt hybrid seeds at 90x60 cm. One seed per hill. Sow 20% non-Bt refuge on border.",
                "priority": "critical",
            },
            {
                "week": 3,
                "month": "May",
                "start_day": 15,
                "task": "Gap filling and first irrigation",
                "details": "Fill gaps at 10-15 DAS. First irrigation if no rain for support of young plants.",
                "priority": "high",
            },
            {
                "week": 4,
                "month": "June",
                "start_day": 1,
                "task": "First top-dressing + hoeing",
                "details": "Apply 1/4 N at 20-25 DAS. Interculture with hoe for weed control.",
                "priority": "high",
            },
            {
                "week": 5,
                "month": "June",
                "start_day": 20,
                "task": "Second top-dressing at squaring",
                "details": "Apply 1/4 N + remaining K at 40 DAS. Earth up for support.",
                "priority": "critical",
            },
            {
                "week": 6,
                "month": "July",
                "start_day": 10,
                "task": "Sucking pest management",
                "details": "Monitor for whitefly, jassids, thrips. Spray if threshold crossed. Avoid broad-spectrum.",
                "priority": "high",
            },
            {
                "week": 7,
                "month": "August",
                "start_day": 1,
                "task": "Third top-dressing + bollworm scout",
                "details": "Apply 1/4 N at flowering (65 DAS). Check for bollworm entry holes in squares/bolls.",
                "priority": "critical",
            },
            {
                "week": 8,
                "month": "August",
                "start_day": 20,
                "task": "Fourth top-dressing + boll care",
                "details": "Apply remaining 1/4 N at 85 DAS. Spray for bollworm if needed.",
                "priority": "high",
            },
            {
                "week": 9,
                "month": "September",
                "start_day": 15,
                "task": "First picking",
                "details": "Pick only fully opened bolls. Pick in dry conditions. Separate good and stained cotton.",
                "priority": "high",
            },
            {
                "week": 10,
                "month": "October",
                "start_day": 1,
                "task": "Subsequent pickings (2nd-4th)",
                "details": "Pick every 15-20 days. Continue till December for late bolls.",
                "priority": "high",
            },
        ],
    },
    "potato": {
        "rabi": [
            {
                "week": 1,
                "month": "October",
                "start_day": 1,
                "task": "Field preparation",
                "details": "Deep ploughing + 2-3 harrowings. Apply FYM @ 25 t/ha. Make ridges at 60 cm.",
                "priority": "high",
            },
            {
                "week": 2,
                "month": "October",
                "start_day": 15,
                "task": "Seed tuber preparation and planting",
                "details": "Plant 25-50 g tubers at 60x20 cm on ridges. Apply 2/3 N + full P + full K as basal.",
                "priority": "critical",
            },
            {
                "week": 3,
                "month": "November",
                "start_day": 1,
                "task": "First irrigation + weed management",
                "details": "Light irrigation at 3-4 DAP. Spray Metribuzin @ 1 g/L pre-emergence for weeds.",
                "priority": "high",
            },
            {
                "week": 4,
                "month": "November",
                "start_day": 15,
                "task": "Earthing up + top-dressing",
                "details": "Earth up at 30 DAP. Apply remaining 1/3 N. Cover tubers completely to prevent greening.",
                "priority": "critical",
            },
            {
                "week": 5,
                "month": "December",
                "start_day": 1,
                "task": "Late blight prevention spray",
                "details": "Prophylactic spray of Mancozeb @ 2.5 g/L every 10-12 days during foggy weather.",
                "priority": "high",
            },
            {
                "week": 6,
                "month": "December",
                "start_day": 15,
                "task": "Tuber bulking — regular irrigation",
                "details": "Irrigate every 7-10 days. Maintain 70-80% field capacity. Scout for late blight.",
                "priority": "critical",
            },
            {
                "week": 7,
                "month": "January",
                "start_day": 5,
                "task": "Aphid monitoring and dehaulming (for seed crop)",
                "details": "Check for aphids. Cut haulms by Jan end for seed crop to prevent virus spread.",
                "priority": "high",
            },
            {
                "week": 8,
                "month": "January",
                "start_day": 25,
                "task": "Harvesting",
                "details": "Harvest when haulms dry and skin doesn't peel. Cure at 15-20°C for 10 days before storage.",
                "priority": "critical",
            },
        ],
    },
    "sugarcane": {
        "spring": [
            {
                "week": 1,
                "month": "February",
                "start_day": 1,
                "task": "Field preparation",
                "details": "Deep ploughing + 2-3 harrowings. Open furrows at 75-90 cm. Apply FYM @ 25 t/ha.",
                "priority": "high",
            },
            {
                "week": 2,
                "month": "February",
                "start_day": 20,
                "task": "Planting setts with basal fertilizer",
                "details": "Plant 3-bud setts end-to-end in furrows. Apply full P + full K in furrows. Irrigate immediately.",
                "priority": "critical",
            },
            {
                "week": 3,
                "month": "March",
                "start_day": 10,
                "task": "Gap filling and light irrigation",
                "details": "Fill gaps at 30 DAP with pre-germinated setts. Irrigate every 7 days.",
                "priority": "high",
            },
            {
                "week": 4,
                "month": "March",
                "start_day": 25,
                "task": "First top-dressing + earthing up",
                "details": "Apply 1/3 N (115 kg urea/ha) at 30 DAP with first earthing up.",
                "priority": "critical",
            },
            {
                "week": 5,
                "month": "April",
                "start_day": 20,
                "task": "Second top-dressing + earthing up",
                "details": "Apply 1/3 N at 60 DAP with second earthing up. Interculture for weeds.",
                "priority": "critical",
            },
            {
                "week": 6,
                "month": "May",
                "start_day": 15,
                "task": "Third top-dressing + trash mulching",
                "details": "Apply remaining 1/3 N at 90 DAP. Final earthing up. Mulch with dry leaves in furrows.",
                "priority": "high",
            },
            {
                "week": 7,
                "month": "June",
                "start_day": 1,
                "task": "Grand growth phase — regular irrigation",
                "details": "Maximum water requirement period. Irrigate every 7-10 days. Tie canes if lodging.",
                "priority": "critical",
            },
            {
                "week": 8,
                "month": "July",
                "start_day": 1,
                "task": "Pest scouting (borer, pyrilla)",
                "details": "Release Trichogramma cards for borer. Check for pyrilla (leaf hopper).",
                "priority": "medium",
            },
            {
                "week": 9,
                "month": "September",
                "start_day": 1,
                "task": "Tying and propping",
                "details": "Tie canes to prevent lodging during monsoon winds. Remove dried leaves.",
                "priority": "medium",
            },
            {
                "week": 10,
                "month": "December",
                "start_day": 1,
                "task": "Withhold irrigation before harvest",
                "details": "Stop irrigation 15-20 days before harvest to increase sugar content.",
                "priority": "high",
            },
            {
                "week": 11,
                "month": "January",
                "start_day": 1,
                "task": "Harvesting",
                "details": "Cut at ground level. Remove green tops. Crush within 24-48 hours for best recovery.",
                "priority": "critical",
            },
        ],
    },
}

FAQ_DATA: list[dict[str, Any]] = [
    {
        "id": 1,
        "topic": "soil_health",
        "question": "How often should I get my soil tested?",
        "answer": "Get your soil tested every 2 years before the sowing season. Under the Soil Health Card scheme, the government provides free testing. Collect samples from 6-8 spots at 15 cm depth, mix them, and send 500 g to the nearest soil testing lab. This helps optimize fertilizer use and can save Rs 2,000-3,000/ha.",
    },
    {
        "id": 2,
        "topic": "fertilizer",
        "question": "How much urea should I apply to wheat?",
        "answer": "For irrigated timely-sown wheat, the total nitrogen recommendation is 120 kg N/ha (about 260 kg urea/ha). Apply in 2 splits: half at sowing as basal and half at the first irrigation (CRI stage, 21 days after sowing). Never apply all urea at once — it causes lodging and is inefficient.",
    },
    {
        "id": 3,
        "topic": "irrigation",
        "question": "Which is the most critical irrigation for wheat?",
        "answer": "The Crown Root Initiation (CRI) stage irrigation at 21 days after sowing is the most critical. Skipping this single irrigation can reduce yield by 30-40%. If you can only irrigate once, always irrigate at CRI. The second most important is at flowering (80-85 DAS).",
    },
    {
        "id": 4,
        "topic": "pest_management",
        "question": "How do I identify and control yellow rust in wheat?",
        "answer": "Yellow rust appears as yellow-orange powdery stripes on the upper surface of leaves, usually during January-February when temperatures are 10-15°C with high humidity. Spray Propiconazole 25 EC @ 1 ml/L or Tebuconazole 250 EC @ 1 ml/L. Use 500 L water per hectare. Repeat after 15 days if needed. Prevention: sow resistant varieties like HD 3226 or PBW 826.",
    },
    {
        "id": 5,
        "topic": "schemes",
        "question": "How can I apply for PM-KISAN?",
        "answer": "Visit pmkisan.gov.in or your village panchayat/Common Service Centre. You need: Aadhaar card, Aadhaar-linked bank account, and land records (khatauni). The scheme gives Rs 6,000/year in 3 installments of Rs 2,000 each directly to your bank account. All landholding families are eligible except income tax payers and government employees.",
    },
    {
        "id": 6,
        "topic": "schemes",
        "question": "What is the benefit of Kisan Credit Card?",
        "answer": "KCC provides short-term crop loans at just 4% interest (with prompt repayment subvention) against the normal 7-9%. You get a credit limit up to Rs 3 lakh without collateral. It can be used for crop production costs, post-harvest expenses, and even allied activities like dairy. Apply at any bank branch with your Aadhaar, land records, and passport photo.",
    },
    {
        "id": 7,
        "topic": "market_info",
        "question": "What is MSP and how do I sell at MSP?",
        "answer": "MSP (Minimum Support Price) is the guaranteed minimum price at which the government buys your produce. To sell at MSP: 1) Register on your state's procurement portal before the season. 2) Bring your produce to the designated APMC mandi or procurement centre. 3) Ensure quality standards are met (moisture content, foreign matter). FCI buys wheat and rice; NAFED buys pulses and oilseeds.",
    },
    {
        "id": 8,
        "topic": "organic_farming",
        "question": "How can I start organic farming?",
        "answer": "Start the transition: 1) Get soil tested. 2) Prepare compost (NADEP/vermi) — you need 5-8 tonnes/ha. 3) Replace chemical fertilizers gradually with FYM, vermicompost, Jeevamrut, and Panchagavya. 4) Use neem-based pesticides and bio-agents (Trichoderma, Pseudomonas). 5) Register under Paramparagat Krishi Vikas Yojana (PKVY) for Rs 50,000/ha assistance over 3 years. Full conversion takes 3 years for organic certification.",
    },
    {
        "id": 9,
        "topic": "irrigation",
        "question": "What are the benefits of drip irrigation?",
        "answer": "Drip irrigation saves 30-50% water compared to flood irrigation, increases yield by 20-30%, reduces fertilizer use (with fertigation), and decreases weed growth. It is especially beneficial for sugarcane, cotton, vegetables, and fruits. Under PM Krishi Sinchayee Yojana, small/marginal farmers get 55% subsidy on drip systems. Apply through your District Agriculture/Horticulture Office.",
    },
    {
        "id": 10,
        "topic": "general",
        "question": "How do I register on e-NAM?",
        "answer": "Register on enam.gov.in or through the e-NAM mobile app. You need: Aadhaar card, bank account details, and a mandi license (or register through your Farmer Producer Organization). e-NAM allows you to see real-time prices across mandis in India, get competitive bids for your produce, and receive payment directly to your bank account. Over 1,000 mandis across 18 states are connected.",
    },
    {
        "id": 11,
        "topic": "pest_management",
        "question": "How to control fall armyworm in maize?",
        "answer": "Identify: Large caterpillar with inverted Y-mark on head, feeding inside the whorl. Control: Spray Spinetoram 11.7 SC @ 0.5 ml/L or Emamectin benzoate 5 SG @ 0.4 g/L directly into the whorl. For biological control, release Trichogramma chilonis egg parasitoid cards at 1 lakh eggs/ha. Scout weekly from crop emergence. Use pheromone traps (5/ha) for adult monitoring.",
    },
    {
        "id": 12,
        "topic": "sowing",
        "question": "What is the best time to sow wheat in North India?",
        "answer": "The optimal sowing window for wheat in North India is November 1-25. Timely sowing yields 40-55 q/ha. Late sowing (after Nov 25) reduces yield by 30-40 kg/ha for each week of delay. For late sowing, use short-duration varieties (HD 3059, PBW 771) and increase seed rate by 25% (125-150 kg/ha). Very late sowing beyond December 25 is not recommended.",
    },
]

# ============================================================
# Intent Detection
# ============================================================

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "fertilizer_advice": [
        "fertilizer",
        "fertiliser",
        "urea",
        "dap",
        "npk",
        "mop",
        "potash",
        "khad",
        "khaad",
        "nitrogen",
        "phosphorus",
        "phosphorous",
        "manure",
        "compost",
        "nutrient",
        "zinc",
        "sulphur",
        "micronutrient",
        "top dressing",
        "top-dressing",
        "basal dose",
    ],
    "irrigation_advice": [
        "irrigation",
        "irrigate",
        "water",
        "watering",
        "paani",
        "pani",
        "sinchai",
        "drip",
        "sprinkler",
        "flood",
        "moisture",
        "dry",
        "drought",
        "submergence",
        "waterlogging",
        "rauni",
        "palewa",
    ],
    "pest_management": [
        "pest",
        "insect",
        "disease",
        "fungus",
        "fungal",
        "virus",
        "bacteria",
        "rog",
        "keeda",
        "kida",
        "kira",
        "bimari",
        "rust",
        "blight",
        "wilt",
        "aphid",
        "borer",
        "armyworm",
        "whitefly",
        "bollworm",
        "mite",
        "yellowing",
        "spots",
        "pustules",
        "caterpillar",
        "sundi",
        "makor",
        "spray",
        "pesticide",
        "fungicide",
        "insecticide",
        "dawai",
        "dawa",
    ],
    "government_schemes": [
        "scheme",
        "yojana",
        "yojna",
        "subsidy",
        "sarkari",
        "government",
        "pm-kisan",
        "pmkisan",
        "fasal bima",
        "pmfby",
        "kusum",
        "kcc",
        "credit card",
        "insurance",
        "bima",
        "loan",
        "rin",
        "sahayata",
        "anudaan",
        "grant",
        "benefit",
        "apply",
        "registration",
    ],
    "sowing_advice": [
        "sow",
        "sowing",
        "seed",
        "plant",
        "planting",
        "biyaj",
        "beej",
        "variety",
        "varieties",
        "kiasm",
        "spacing",
        "depth",
        "nursery",
        "transplant",
        "transplanting",
        "seed rate",
        "seed treatment",
        "when to sow",
        "kab bona",
        "kab lagana",
        "rogai",
    ],
    "harvest_advice": [
        "harvest",
        "harvesting",
        "katai",
        "cutting",
        "reaping",
        "yield",
        "upaj",
        "paidawar",
        "threshing",
        "storage",
        "post-harvest",
        "combine",
        "post harvest",
        "store",
        "godown",
    ],
    "market_info": [
        "price",
        "mandi",
        "market",
        "msp",
        "sell",
        "selling",
        "rate",
        "bhav",
        "daam",
        "dam",
        "procurement",
        "enam",
        "e-nam",
        "frp",
        "buyers",
        "buyer",
        "trade",
        "trading",
        "auction",
    ],
}

KNOWN_CROPS: list[str] = [
    "wheat",
    "rice",
    "paddy",
    "maize",
    "corn",
    "sugarcane",
    "ganna",
    "mustard",
    "sarson",
    "cotton",
    "kapas",
    "potato",
    "aloo",
    "soybean",
    "pulses",
    "chana",
    "dal",
    "moong",
    "tur",
    "arhar",
    "bajra",
    "jowar",
    "ragi",
    "barley",
    "jau",
    "groundnut",
    "mungfali",
    "sunflower",
    "til",
    "sesame",
]

# Canonical name mapping for aliases
_CROP_ALIASES: dict[str, str] = {
    "paddy": "rice",
    "chawal": "rice",
    "dhan": "rice",
    "gehun": "wheat",
    "gehu": "wheat",
    "corn": "maize",
    "makka": "maize",
    "makki": "maize",
    "bhutta": "maize",
    "ganna": "sugarcane",
    "ikshu": "sugarcane",
    "sarson": "mustard",
    "rai": "mustard",
    "kapas": "cotton",
    "rui": "cotton",
    "aloo": "potato",
    "batata": "potato",
    "jau": "barley",
    "mungfali": "groundnut",
    "moongfali": "groundnut",
    "til": "sesame",
}


def _detect_intent(message: str) -> str:
    """Detect the user's intent from their message using keyword matching."""
    msg = message.lower()
    scores: dict[str, int] = defaultdict(int)
    for intent, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in msg:
                scores[intent] += 1
    if not scores:
        return "general"
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def _extract_crop(message: str, context: dict[str, Any] | None = None) -> str | None:
    """Extract a crop name from the message or context."""
    msg = message.lower()

    # Check context first
    if context and context.get("crop"):
        crop = context["crop"].lower()
        return _CROP_ALIASES.get(crop, crop)

    # Search for crop names in the message
    for crop in KNOWN_CROPS:
        # Word boundary match to avoid partial matches
        if re.search(rf"\b{re.escape(crop)}\b", msg):
            return _CROP_ALIASES.get(crop, crop)

    # Check aliases
    for alias, canonical in _CROP_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", msg):
            return canonical

    return None


# ============================================================
# Response Formatters
# ============================================================


def _format_fertilizer(crop: str) -> dict[str, Any]:
    data = FARMING_KNOWLEDGE["fertilizer"].get(crop)
    if not data:
        return {
            "text": f"Detailed fertilizer recommendations for '{crop}' are not yet in our database. "
            f"General guideline: get a soil test done under the Soil Health Card scheme and follow "
            f"the crop-wise nutrient recommendations on your card.",
            "sources": [{"type": "knowledge_base", "topic": "general_fertilizer"}],
            "actions": ["Get soil test done", "Visit Soil Health Card portal"],
        }

    lines = [f"Fertilizer recommendation for {crop.title()}:"]
    lines.append(f"  Total NPK: {data.get('total_npk', 'N/A')}")
    if "schedule" in data:
        lines.append("  Application schedule:")
        for step in data["schedule"]:
            lines.append(f"    - {step}")

    return {
        "text": "\n".join(lines),
        "sources": [{"type": "knowledge_base", "topic": f"{crop}_fertilizer"}],
        "actions": [
            "Get soil tested for customized recommendation",
            f"View full {crop.title()} crop calendar",
            "Check fertilizer prices at nearest dealer",
        ],
    }


def _format_irrigation(crop: str) -> dict[str, Any]:
    data = FARMING_KNOWLEDGE["irrigation"].get(crop)
    if not data:
        return {
            "text": f"Irrigation details for '{crop}' are not yet available. General rule: irrigate at "
            f"critical growth stages (flowering, grain filling) and avoid waterlogging.",
            "sources": [{"type": "knowledge_base", "topic": "general_irrigation"}],
            "actions": [
                "Check weather forecast",
                "Explore drip irrigation subsidy under PMKSY",
            ],
        }

    lines = [f"Irrigation guide for {crop.title()}:"]
    lines.append(f"  Total water: {data['total']}")
    lines.append(f"  Critical stages: {data['critical_stages']}")
    if "schedule" in data:
        lines.append("  Schedule:")
        for s in data["schedule"]:
            priority_label = s["priority"].upper()
            lines.append(f"    [{priority_label}] {s['stage']}: {s['note']}")
    if "note" in data:
        lines.append(f"  Tip: {data['note']}")

    return {
        "text": "\n".join(lines),
        "sources": [{"type": "knowledge_base", "topic": f"{crop}_irrigation"}],
        "actions": [
            "Check weather forecast for rain",
            "Explore PMKSY subsidy for drip/sprinkler",
            f"View {crop.title()} crop calendar",
        ],
    }


def _format_pest_management(crop: str, message: str) -> dict[str, Any]:
    data = FARMING_KNOWLEDGE["pest_management"].get(crop)
    if not data:
        return {
            "text": f"Pest/disease data for '{crop}' is not yet in our database. General advice: "
            f"scout your field regularly, identify the pest correctly before spraying, and use "
            f"recommended pesticides at correct dosage. Contact your nearest Krishi Vigyan Kendra (KVK) "
            f"for diagnosis.",
            "sources": [{"type": "knowledge_base", "topic": "general_pest"}],
            "actions": [
                "Contact nearest KVK",
                "Send a photo to agriculture helpline 1551",
            ],
        }

    msg = message.lower()
    # Try to match a specific pest/disease
    matched_pest = None
    for pest_key, pest_info in data.items():
        if pest_key.replace("_", " ") in msg or pest_key in msg:
            matched_pest = (pest_key, pest_info)
            break
    # Also check symptoms keywords
    if not matched_pest:
        for pest_key, pest_info in data.items():
            symptoms_lower = pest_info.get("symptoms", "").lower()
            # Check if any distinctive symptom word is in the message
            symptom_words = [w for w in symptoms_lower.split() if len(w) > 4]
            for sw in symptom_words:
                if sw in msg:
                    matched_pest = (pest_key, pest_info)
                    break
            if matched_pest:
                break

    if matched_pest:
        name, info = matched_pest
        lines = [f"Pest/Disease: {name.replace('_', ' ').title()} in {crop.title()}"]
        lines.append(f"  Symptoms: {info['symptoms']}")
        lines.append(f"  Favorable conditions: {info['conditions']}")
        lines.append(f"  Control: {info['control']}")
        lines.append(f"  Prevention: {info['prevention']}")
    else:
        lines = [f"Common pests and diseases of {crop.title()}:"]
        for pest_key, pest_info in data.items():
            lines.append(f"\n  {pest_key.replace('_', ' ').title()}:")
            lines.append(f"    Symptoms: {pest_info['symptoms']}")
            lines.append(f"    Control: {pest_info['control']}")

    return {
        "text": "\n".join(lines),
        "sources": [{"type": "knowledge_base", "topic": f"{crop}_pest_management"}],
        "actions": [
            "Send a photo to KVK for exact diagnosis",
            "Purchase recommended spray from agri-input dealer",
            "Call agriculture helpline 1551",
        ],
    }


def _format_sowing(crop: str) -> dict[str, Any]:
    data = FARMING_KNOWLEDGE["sowing"].get(crop)
    if not data:
        return {
            "text": f"Sowing information for '{crop}' is not yet available. Contact your local Krishi "
            f"Vigyan Kendra or agriculture university for region-specific recommendations.",
            "sources": [{"type": "knowledge_base", "topic": "general_sowing"}],
            "actions": [
                "Contact nearest KVK",
                "Visit state agriculture university website",
            ],
        }

    lines = [f"Sowing guide for {crop.title()}:"]
    for season, info in data.items():
        lines.append(f"\n  Season: {season.title()}")
        lines.append(
            f"    Optimal sowing date: {info.get('optimal_date_range', 'N/A')}"
        )
        lines.append(f"    Seed rate: {info.get('seed_rate', 'N/A')}")
        if info.get("seed_treatment"):
            lines.append(f"    Seed treatment: {info['seed_treatment']}")
        lines.append(f"    Spacing: {info.get('spacing', 'N/A')}")
        if info.get("soil_preparation"):
            lines.append(f"    Soil preparation: {info['soil_preparation']}")
        if info.get("varieties"):
            lines.append("    Recommended varieties:")
            for region, varieties in info["varieties"].items():
                if isinstance(varieties, list):
                    lines.append(
                        f"      {region.replace('_', ' ').title()}: {', '.join(varieties)}"
                    )
                else:
                    lines.append(
                        f"      {region.replace('_', ' ').title()}: {varieties}"
                    )

    return {
        "text": "\n".join(lines),
        "sources": [{"type": "knowledge_base", "topic": f"{crop}_sowing"}],
        "actions": [
            "Purchase certified seed from authorized dealer",
            "Get soil tested before sowing",
            f"View {crop.title()} crop calendar",
        ],
    }


def _format_harvest(crop: str) -> dict[str, Any]:
    data = FARMING_KNOWLEDGE["harvest"].get(crop)
    if not data:
        return {
            "text": f"Harvest information for '{crop}' is not yet available. General advice: harvest when "
            f"the crop shows full maturity signs and moisture is at the recommended level for your crop.",
            "sources": [{"type": "knowledge_base", "topic": "general_harvest"}],
            "actions": ["Contact KVK", "Check mandi rates before selling"],
        }

    lines = [f"Harvest guide for {crop.title()}:"]
    lines.append(f"  When to harvest: {data['timing']}")
    lines.append(f"  Crop duration: {data['duration']}")
    lines.append(f"  Harvesting method: {data['method']}")
    lines.append(f"  Post-harvest: {data['post_harvest']}")
    lines.append(f"  Expected yield: {data['yield']}")

    return {
        "text": "\n".join(lines),
        "sources": [{"type": "knowledge_base", "topic": f"{crop}_harvest"}],
        "actions": [
            "Check current mandi prices on e-NAM",
            "Book combine harvester",
            "Check MSP and procurement dates",
        ],
    }


def _format_market(crop: str) -> dict[str, Any]:
    data = FARMING_KNOWLEDGE["market_info"].get(crop)
    if not data:
        return {
            "text": f"Market information for '{crop}' is not available in our database. Check real-time "
            f"prices on e-NAM (enam.gov.in) or call your nearest APMC mandi for today's rates.",
            "sources": [{"type": "knowledge_base", "topic": "general_market"}],
            "actions": ["Visit enam.gov.in", "Call APMC mandi for today's rates"],
        }

    lines = [f"Market information for {crop.title()}:"]
    if "msp_2025_26" in data:
        lines.append(f"  MSP 2025-26: {data['msp_2025_26']}")
    if "frp_2025_26" in data:
        lines.append(f"  FRP 2025-26: {data['frp_2025_26']}")
    if "sap_note" in data:
        lines.append(f"  SAP note: {data['sap_note']}")
    if "note" in data:
        lines.append(f"  Note: {data['note']}")
    if "average_price" in data:
        lines.append(f"  Average price: {data['average_price']}")
    if "procurement" in data:
        lines.append(f"  Procurement: {data['procurement']}")
    if "tips" in data:
        lines.append(f"  Selling tip: {data['tips']}")

    return {
        "text": "\n".join(lines),
        "sources": [{"type": "knowledge_base", "topic": f"{crop}_market"}],
        "actions": [
            "Register on e-NAM for online trading",
            "Check APMC mandi rates today",
            "Explore warehousing options for better prices",
        ],
    }


def _format_schemes_chat() -> dict[str, Any]:
    lines = ["Here are the major government schemes for farmers:\n"]
    for scheme in GOVERNMENT_SCHEMES[:6]:
        lines.append(f"  {scheme['name']} ({scheme['id'].upper()})")
        lines.append(f"    Benefit: {scheme['benefit']}")
        lines.append(f"    Apply: {scheme['application_url']}")
        lines.append("")

    lines.append(f"  ... and {len(GOVERNMENT_SCHEMES) - 6} more schemes available.")
    lines.append(
        "\nUse the /schemes endpoint or ask about a specific scheme for details."
    )

    return {
        "text": "\n".join(lines),
        "sources": [{"type": "knowledge_base", "topic": "government_schemes"}],
        "actions": [
            "Check PM-KISAN status at pmkisan.gov.in",
            "Apply for Kisan Credit Card at your bank",
            "Visit Common Service Centre for application help",
        ],
    }


def _format_general_response(message: str) -> dict[str, Any]:
    return {
        "text": (
            "I am Kisaan Sahayak, your farming assistant. I can help you with:\n"
            "  1. Fertilizer recommendations (ask about urea, DAP, NPK for your crop)\n"
            "  2. Irrigation schedule (when and how much to water)\n"
            "  3. Pest and disease management (identification and control)\n"
            "  4. Sowing guide (best time, seed rate, varieties)\n"
            "  5. Harvest and post-harvest advice\n"
            "  6. Market prices and MSP information\n"
            "  7. Government schemes (PM-KISAN, PMFBY, KCC, etc.)\n\n"
            "Please mention your crop name (e.g., wheat, rice, maize) along with "
            "your question for the best advice. For example:\n"
            "  'What fertilizer should I use for wheat?'\n"
            "  'When should I irrigate rice?'\n"
            "  'How to control rust in wheat?'"
        ),
        "sources": [],
        "actions": [
            "Ask about fertilizer for your crop",
            "Ask about irrigation schedule",
            "Check government schemes",
        ],
    }


# ============================================================
# Session Management
# ============================================================

# DB: _sessions -> ChatSession, ChatMessage tables

MAX_SESSION_HISTORY = 20


async def _get_or_create_session(
    session_id: str | None, db: AsyncSession
) -> tuple[str, list[dict[str, str]]]:
    session = None
    if session_id:
        result = await db.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()

    if session:
        sid = session.session_id
    else:
        sid = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        db.add(ChatSession(session_id=sid))
        await db.flush()

    messages_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == sid)
        .order_by(ChatMessage.id)
    )
    messages = messages_result.scalars().all()
    history = [message.to_dict() for message in messages]
    return sid, history


async def _add_to_session(
    db: AsyncSession, session_id: str, role: str, content: str
) -> None:
    db.add(ChatMessage(session_id=session_id, role=role, content=content))
    await db.flush()

    # Keep only the last N messages
    old_ids_result = await db.execute(
        select(ChatMessage.id)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .offset(MAX_SESSION_HISTORY)
    )
    old_ids = old_ids_result.scalars().all()
    if old_ids:
        await db.execute(delete(ChatMessage).where(ChatMessage.id.in_(old_ids)))


# ============================================================
# Season Detection
# ============================================================

MONTH_TO_SEASON: dict[int, str] = {
    1: "rabi",
    2: "rabi",
    3: "rabi",
    4: "zaid",
    5: "kharif",
    6: "kharif",
    7: "kharif",
    8: "kharif",
    9: "kharif",
    10: "rabi",
    11: "rabi",
    12: "rabi",
}

# Which season does each crop primarily belong to
_CROP_SEASON: dict[str, str] = {
    "wheat": "rabi",
    "rice": "kharif",
    "maize": "kharif",
    "mustard": "rabi",
    "cotton": "kharif",
    "potato": "rabi",
    "sugarcane": "spring",
}


def _detect_season(crop: str | None, explicit_season: str | None = None) -> str:
    if explicit_season:
        return explicit_season.lower()
    if crop and crop in _CROP_SEASON:
        return _CROP_SEASON[crop]
    now = datetime.now(timezone.utc)
    return MONTH_TO_SEASON.get(now.month, "rabi")


# ============================================================
# Pydantic Models
# ============================================================


class ChatRequest(BaseModel):
    message: str
    language: str = "en"
    session_id: str | None = None
    context: dict[str, Any] | None = None


class ChatSource(BaseModel):
    type: str
    topic: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    language: str
    intent_detected: str
    crop_detected: str | None
    sources: list[ChatSource]
    suggested_actions: list[str]
    model_used: str = "rule-based"
    responded_at: str


class SchemeResponse(BaseModel):
    id: str
    name: str
    description: str
    benefit: str
    eligibility: dict[str, Any]
    application_url: str
    documents_required: list[str]
    crop_specific: bool
    category: str


class SchemesListResponse(BaseModel):
    total: int
    filters_applied: dict[str, str | None]
    schemes: list[SchemeResponse]


class CalendarTask(BaseModel):
    week: int
    month: str
    task: str
    details: str
    priority: str
    status: str = "upcoming"


class CalendarResponse(BaseModel):
    crop: str
    season: str
    region: str
    total_tasks: int
    upcoming_tasks: list[CalendarTask]
    past_tasks: list[CalendarTask]
    current_date: str


class FAQItem(BaseModel):
    id: int
    topic: str
    question: str
    answer: str


class FAQResponse(BaseModel):
    total: int
    topic_filter: str | None
    faqs: list[FAQItem]


# ============================================================
# FastAPI App
# ============================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup resources."""
    # await init_db()
    yield
    await close_db()


app = FastAPI(
    title="Kisaan Sahayak",
    description="Multi-Agent Crop Health & Advisory System for Indian farmers — integrating Vision, Verifier, Weather, Market, Memory, and LLM agents",
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

# auth router already has prefix="/auth" — do NOT add prefix again
app.include_router(auth_router, tags=["auth"])
setup_rate_limiting(app)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": "kisaan_sahayak",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint returning service info."""
    return {
        "service": "Kisaan Sahayak",
        "version": "3.0.0 (Team Annadata Edition)",
        "description": "Multi-Agent Crop Health & Advisory System powered by NVIDIA NIM",
        "llm_status": "active" if _NVIDIA_AVAILABLE else "fallback (rule-based)",
        "features": [
            "Natural language farming Q&A in multiple Indian languages",
            "NVIDIA Llama-3.3 (NIM) enhanced responses with KB grounding",
            "Government scheme eligibility and application assistance",
            "Personalized crop calendar and task reminders",
            "Vision Agent — crop disease classification",
            "Verifier Agent — disease risk assessment",
            "Weather Agent — short-term forecast",
            "Market Agent — nearby mandi prices",
            "Memory Agent — farmer history logging",
            "LLM Agent — WhatsApp-style multilingual summaries via NVIDIA NIM",
            "Full Pipeline — single-request end-to-end analysis",
        ],
        "agents": {
            "vision": "/agent/vision",
            "verifier": "/agent/verify",
            "weather": "/agent/weather",
            "market": "/agent/market",
            "memory_log": "/agent/memory/log",
            "memory_get": "/agent/memory/{farmer_id}",
            "llm": "/agent/llm",
            "pipeline": "/pipeline/analyze",
        },
    }


# ------------------------------------------------------------------
# POST /chat
# ------------------------------------------------------------------


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Process a farming question using KB lookup + NVIDIA NIM enhancement."""
    session_id, history = await _get_or_create_session(request.session_id, db)
    await _add_to_session(db, session_id, "user", request.message)
    history.append({"role": "user", "content": request.message})

    intent = _detect_intent(request.message)
    crop = _extract_crop(request.message, request.context)

    # If no crop from current message, try to get from recent session context
    if not crop and history:
        for entry in reversed(history[:-1]):
            found = _extract_crop(entry["content"])
            if found:
                crop = found
                break

    # ---- Step 1: Rule-based KB lookup (Grounding source) ----
    if intent == "fertilizer_advice":
        result = _format_fertilizer(crop) if crop else None
    elif intent == "irrigation_advice":
        result = _format_irrigation(crop) if crop else None
    elif intent == "pest_management":
        result = _format_pest_management(crop, request.message) if crop else None
    elif intent == "government_schemes":
        result = _format_schemes_chat()
    elif intent == "sowing_advice":
        result = _format_sowing(crop) if crop else None
    elif intent == "harvest_advice":
        result = _format_harvest(crop) if crop else None
    elif intent == "market_info":
        result = _format_market(crop) if crop else None
    else:
        result = None

    # ---- Step 2: Global Context Builder (Dossier) ----
    # If a crop is detected, we get the FULL dossier (Calendar + Nutrients + Mkt)
    # to provide the LLM with a 360-degree view.
    dossier = _get_crop_grounding_context(crop) if crop else ""
    
    # Specific grounding context for the current user intent (if any)
    intent_context = result["text"] if result else ""
    combined_context = f"{dossier}\n\n### Current User Intent Grounding:\n{intent_context}"

    # ---- Step 3: AI-First Response Logic ----
    model_used = "rule-based"
    response_text = result["text"] if result else _format_general_response(request.message)["text"]

    if _NVIDIA_AVAILABLE:
        # AI-First Path: Always try to use NVIDIA NIM for high-quality advisory
        nvidia_response = await _call_nvidia(
            user_message=request.message,
            kb_context=combined_context,
            history=history,
            language=request.language,
        )
        if nvidia_response:
            response_text = nvidia_response
            model_used = "NVIDIA-Llama-3.3-AI-First"
        if nvidia_response:
            response_text = nvidia_response
            model_used = "NVIDIA-Llama-3.3"

    await _add_to_session(db, session_id, "assistant", response_text)

    return ChatResponse(
        session_id=session_id,
        response=response_text,
        language=request.language,
        intent_detected=intent,
        crop_detected=crop,
        sources=[ChatSource(**s) for s in result["sources"]],
        suggested_actions=result["actions"],
        model_used=model_used,
        responded_at=datetime.now(timezone.utc).isoformat(),
    )


# ------------------------------------------------------------------
# GET /schemes
# ------------------------------------------------------------------


@app.get("/schemes", response_model=SchemesListResponse)
async def get_government_schemes(
    state: str | None = Query(
        None, description="Filter by state (e.g., 'Punjab', 'Maharashtra')"
    ),
    category: str | None = Query(
        None, description="Farmer category: small_marginal, medium, large"
    ),
    crop: str | None = Query(None, description="Filter for crop-specific schemes"),
):
    """Get relevant government schemes, optionally filtered by state, farmer category, and crop."""
    filtered = GOVERNMENT_SCHEMES

    # Filter by farmer category
    if category:
        category_lower = category.lower().strip()
        filtered = [
            s
            for s in filtered
            if category_lower in s["eligibility"].get("category", [])
        ]

    # Filter by crop relevance (only return crop-specific if crop given, plus all general)
    if crop:
        crop_lower = crop.lower().strip()
        crop_lower = _CROP_ALIASES.get(crop_lower, crop_lower)
        filtered = [
            s
            for s in filtered
            if not s["crop_specific"]  # always include non-crop-specific schemes
            or crop_lower in s.get("name", "").lower()
            or crop_lower in s.get("description", "").lower()
        ]

    # State filter — most schemes are "all"; this is a placeholder for state-specific filtering
    if state:
        state_lower = state.lower().strip()
        filtered = [
            s
            for s in filtered
            if s["applicable_states"] == "all"
            or state_lower in str(s.get("applicable_states", "")).lower()
        ]

    return SchemesListResponse(
        total=len(filtered),
        filters_applied={"state": state, "category": category, "crop": crop},
        schemes=[
            SchemeResponse(
                id=s["id"],
                name=s["name"],
                description=s["description"],
                benefit=s["benefit"],
                eligibility=s["eligibility"],
                application_url=s["application_url"],
                documents_required=s["documents_required"],
                crop_specific=s["crop_specific"],
                category=s["category"],
            )
            for s in filtered
        ],
    )


# ------------------------------------------------------------------
# GET /calendar/{crop}
# ------------------------------------------------------------------


@app.get("/calendar/{crop}", response_model=CalendarResponse)
async def get_crop_calendar(
    crop: str,
    region: str = Query(
        "north_india",
        description="Region: north_india, central_india, south_india, east_india",
    ),
    season: str | None = Query(
        None,
        description="Season: rabi, kharif, zaid, spring. Auto-detected if omitted.",
    ),
):
    """Get personalized crop calendar with tasks classified as past or upcoming based on current date."""
    crop_lower = crop.lower().strip()
    crop_lower = _CROP_ALIASES.get(crop_lower, crop_lower)

    detected_season = _detect_season(crop_lower, season)

    calendar_data = CROP_CALENDAR.get(crop_lower, {})
    tasks = calendar_data.get(detected_season, [])

    if not tasks:
        available_seasons = list(calendar_data.keys()) if calendar_data else []
        hint = ""
        if available_seasons:
            hint = (
                f" Available seasons for {crop_lower}: {', '.join(available_seasons)}."
            )
            # Try returning first available season
            detected_season = available_seasons[0]
            tasks = calendar_data[detected_season]
        else:
            return CalendarResponse(
                crop=crop_lower,
                season=detected_season,
                region=region,
                total_tasks=0,
                upcoming_tasks=[],
                past_tasks=[],
                current_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )

    now = datetime.now(timezone.utc)
    month_map = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }

    upcoming: list[CalendarTask] = []
    past: list[CalendarTask] = []

    for task in tasks:
        task_month_num = month_map.get(task["month"].lower(), 1)
        task_day = task.get("start_day", 1)

        # Determine the year for this task; account for calendars spanning year boundaries
        # Heuristic: if current month is in Q4 and task month is in Q1, task is next year
        # If current month is in Q1-Q2 and task month is in Q4, task was previous year
        task_year = now.year
        if now.month >= 10 and task_month_num <= 4:
            task_year = now.year + 1
        elif now.month <= 4 and task_month_num >= 10:
            task_year = now.year - 1

        try:
            task_date = datetime(
                task_year, task_month_num, task_day, tzinfo=timezone.utc
            )
        except ValueError:
            task_date = datetime(task_year, task_month_num, 1, tzinfo=timezone.utc)

        is_past = task_date < now
        ct = CalendarTask(
            week=task["week"],
            month=task["month"],
            task=task["task"],
            details=task["details"],
            priority=task["priority"],
            status="completed" if is_past else "upcoming",
        )
        if is_past:
            past.append(ct)
        else:
            upcoming.append(ct)

    return CalendarResponse(
        crop=crop_lower,
        season=detected_season,
        region=region,
        total_tasks=len(tasks),
        upcoming_tasks=upcoming,
        past_tasks=past,
        current_date=now.strftime("%Y-%m-%d"),
    )


# ------------------------------------------------------------------
# GET /faq
# ------------------------------------------------------------------


@app.get("/faq", response_model=FAQResponse)
async def get_faq(
    topic: str | None = Query(
        None,
        description="Filter by topic: soil_health, fertilizer, irrigation, pest_management, schemes, market_info, organic_farming, sowing, general",
    ),
):
    """Return frequently asked questions, optionally filtered by topic."""
    if topic:
        topic_lower = topic.lower().strip()
        filtered = [f for f in FAQ_DATA if f["topic"] == topic_lower]
    else:
        filtered = FAQ_DATA

    return FAQResponse(
        total=len(filtered),
        topic_filter=topic,
        faqs=[FAQItem(**f) for f in filtered],
    )


# ============================================================
# Multi-Agent Pipeline: Knowledge Bases
# ============================================================

# PlantVillage 38-class disease mapping (MobileNetV2/ResNet simulation)
# Source: PlantVillage dataset — 54K images, 38 disease classes
PLANTVILLAGE_CLASSES: list[dict[str, Any]] = [
    {
        "index": 0,
        "label": "Apple___Apple_scab",
        "crop": "apple",
        "disease": "Apple Scab",
        "treatment": "Apply Captan 50 WP @ 2 g/L or Mancozeb 75 WP @ 2.5 g/L. Rake and destroy fallen leaves.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 1,
        "label": "Apple___Black_rot",
        "crop": "apple",
        "disease": "Black Rot",
        "treatment": "Prune infected branches. Spray Thiophanate-methyl @ 1 g/L during early season.",
        "severity_base": "HIGH",
    },
    {
        "index": 2,
        "label": "Apple___Cedar_apple_rust",
        "crop": "apple",
        "disease": "Cedar Apple Rust",
        "treatment": "Apply Myclobutanil @ 0.5 ml/L. Remove nearby juniper hosts within 1 km radius.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 3,
        "label": "Apple___healthy",
        "crop": "apple",
        "disease": "Healthy",
        "treatment": "No treatment needed. Continue regular monitoring.",
        "severity_base": "LOW",
    },
    {
        "index": 4,
        "label": "Blueberry___healthy",
        "crop": "blueberry",
        "disease": "Healthy",
        "treatment": "No treatment needed. Maintain soil pH 4.5-5.5.",
        "severity_base": "LOW",
    },
    {
        "index": 5,
        "label": "Cherry___Powdery_mildew",
        "crop": "cherry",
        "disease": "Powdery Mildew",
        "treatment": "Spray Sulphur 80 WP @ 3 g/L or Hexaconazole 5 EC @ 2 ml/L. Improve air circulation.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 6,
        "label": "Cherry___healthy",
        "crop": "cherry",
        "disease": "Healthy",
        "treatment": "No treatment needed. Regular pruning for air flow.",
        "severity_base": "LOW",
    },
    {
        "index": 7,
        "label": "Corn___Cercospora_leaf_spot",
        "crop": "maize",
        "disease": "Cercospora Leaf Spot (Gray Leaf Spot)",
        "treatment": "Apply Azoxystrobin 23 SC @ 1 ml/L. Rotate with non-host crops. Use resistant hybrids.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 8,
        "label": "Corn___Common_rust",
        "crop": "maize",
        "disease": "Common Rust",
        "treatment": "Spray Mancozeb 75 WP @ 2.5 g/L or Propiconazole 25 EC @ 1 ml/L at early infection.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 9,
        "label": "Corn___Northern_Leaf_Blight",
        "crop": "maize",
        "disease": "Northern Leaf Blight",
        "treatment": "Apply Propiconazole 25 EC @ 1 ml/L. Use resistant varieties like DHM 121.",
        "severity_base": "HIGH",
    },
    {
        "index": 10,
        "label": "Corn___healthy",
        "crop": "maize",
        "disease": "Healthy",
        "treatment": "No treatment needed. Continue fall armyworm scouting.",
        "severity_base": "LOW",
    },
    {
        "index": 11,
        "label": "Grape___Black_rot",
        "crop": "grape",
        "disease": "Black Rot",
        "treatment": "Spray Mancozeb @ 2.5 g/L pre-bloom. Remove mummified berries. Ensure good drainage.",
        "severity_base": "HIGH",
    },
    {
        "index": 12,
        "label": "Grape___Esca_(Black_Measles)",
        "crop": "grape",
        "disease": "Esca (Black Measles)",
        "treatment": "No effective chemical cure. Remove infected cordons. Apply wound sealant after pruning.",
        "severity_base": "CRITICAL",
    },
    {
        "index": 13,
        "label": "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)",
        "crop": "grape",
        "disease": "Leaf Blight (Isariopsis)",
        "treatment": "Spray Copper oxychloride 50 WP @ 3 g/L. Improve canopy management.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 14,
        "label": "Grape___healthy",
        "crop": "grape",
        "disease": "Healthy",
        "treatment": "No treatment needed. Maintain canopy for air circulation.",
        "severity_base": "LOW",
    },
    {
        "index": 15,
        "label": "Orange___Haunglongbing_(Citrus_greening)",
        "crop": "orange",
        "disease": "Huanglongbing (Citrus Greening)",
        "treatment": "No cure available. Remove infected trees immediately. Control Asian citrus psyllid vector with Imidacloprid @ 0.5 ml/L.",
        "severity_base": "CRITICAL",
    },
    {
        "index": 16,
        "label": "Peach___Bacterial_spot",
        "crop": "peach",
        "disease": "Bacterial Spot",
        "treatment": "Apply Copper hydroxide 77 WP @ 2 g/L. Avoid overhead irrigation. Use resistant cultivars.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 17,
        "label": "Peach___healthy",
        "crop": "peach",
        "disease": "Healthy",
        "treatment": "No treatment needed. Thin fruits for better size.",
        "severity_base": "LOW",
    },
    {
        "index": 18,
        "label": "Pepper_bell___Bacterial_spot",
        "crop": "pepper",
        "disease": "Bacterial Spot",
        "treatment": "Spray Streptocycline @ 0.5 g/L + Copper oxychloride @ 3 g/L. Use disease-free seed.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 19,
        "label": "Pepper_bell___healthy",
        "crop": "pepper",
        "disease": "Healthy",
        "treatment": "No treatment needed. Maintain balanced nutrition.",
        "severity_base": "LOW",
    },
    {
        "index": 20,
        "label": "Potato___Early_blight",
        "crop": "potato",
        "disease": "Early Blight",
        "treatment": "Spray Mancozeb 75 WP @ 2.5 g/L every 10 days. Maintain proper plant spacing. Avoid overhead irrigation.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 21,
        "label": "Potato___Late_blight",
        "crop": "potato",
        "disease": "Late Blight",
        "treatment": "Spray Cymoxanil + Mancozeb @ 3 g/L curative. Preventive: Mancozeb @ 2.5 g/L every 7-10 days in foggy weather. Use resistant varieties like Kufri Badshah.",
        "severity_base": "CRITICAL",
    },
    {
        "index": 22,
        "label": "Potato___healthy",
        "crop": "potato",
        "disease": "Healthy",
        "treatment": "No treatment needed. Continue late blight vigilance in foggy weather.",
        "severity_base": "LOW",
    },
    {
        "index": 23,
        "label": "Raspberry___healthy",
        "crop": "raspberry",
        "disease": "Healthy",
        "treatment": "No treatment needed. Prune old canes after fruiting.",
        "severity_base": "LOW",
    },
    {
        "index": 24,
        "label": "Rice___Brown_spot",
        "crop": "rice",
        "disease": "Brown Spot",
        "treatment": "Spray Mancozeb 75 WP @ 2.5 g/L or Propiconazole 25 EC @ 1 ml/L. Apply potassium fertilizer to deficient soils.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 25,
        "label": "Rice___Leaf_blast",
        "crop": "rice",
        "disease": "Leaf Blast",
        "treatment": "Spray Tricyclazole 75 WP @ 0.6 g/L or Isoprothiolane 40 EC @ 1.5 ml/L. Use resistant varieties like Pusa Basmati 1847. Balanced nitrogen.",
        "severity_base": "HIGH",
    },
    {
        "index": 26,
        "label": "Rice___Neck_blast",
        "crop": "rice",
        "disease": "Neck Blast",
        "treatment": "Spray Tricyclazole 75 WP @ 0.6 g/L at boot leaf stage preventively. This is the most destructive form — causes broken panicle and total grain loss.",
        "severity_base": "CRITICAL",
    },
    {
        "index": 27,
        "label": "Rice___healthy",
        "crop": "rice",
        "disease": "Healthy",
        "treatment": "No treatment needed. Monitor for blast during cool humid weather.",
        "severity_base": "LOW",
    },
    {
        "index": 28,
        "label": "Soybean___healthy",
        "crop": "soybean",
        "disease": "Healthy",
        "treatment": "No treatment needed. Scout for defoliators.",
        "severity_base": "LOW",
    },
    {
        "index": 29,
        "label": "Squash___Powdery_mildew",
        "crop": "squash",
        "disease": "Powdery Mildew",
        "treatment": "Spray Sulphur 80 WP @ 3 g/L or Dinocap @ 1 ml/L. Ensure proper spacing.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 30,
        "label": "Strawberry___Leaf_scorch",
        "crop": "strawberry",
        "disease": "Leaf Scorch",
        "treatment": "Remove infected leaves. Spray Copper oxychloride @ 3 g/L. Avoid overhead watering.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 31,
        "label": "Strawberry___healthy",
        "crop": "strawberry",
        "disease": "Healthy",
        "treatment": "No treatment needed. Mulch to prevent soil splash.",
        "severity_base": "LOW",
    },
    {
        "index": 32,
        "label": "Tomato___Bacterial_spot",
        "crop": "tomato",
        "disease": "Bacterial Spot",
        "treatment": "Spray Streptocycline @ 0.5 g/L + Copper oxychloride @ 3 g/L. Use disease-free transplants.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 33,
        "label": "Tomato___Early_blight",
        "crop": "tomato",
        "disease": "Early Blight",
        "treatment": "Spray Mancozeb 75 WP @ 2.5 g/L or Chlorothalonil @ 2 g/L. Stake plants for air flow. Remove lower infected leaves.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 34,
        "label": "Tomato___Late_blight",
        "crop": "tomato",
        "disease": "Late Blight",
        "treatment": "Spray Cymoxanil + Mancozeb @ 3 g/L. Destroy infected plants immediately. Avoid overhead irrigation.",
        "severity_base": "CRITICAL",
    },
    {
        "index": 35,
        "label": "Tomato___Leaf_Mold",
        "crop": "tomato",
        "disease": "Leaf Mold",
        "treatment": "Improve greenhouse ventilation. Spray Mancozeb @ 2.5 g/L. Reduce humidity.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 36,
        "label": "Tomato___Septoria_leaf_spot",
        "crop": "tomato",
        "disease": "Septoria Leaf Spot",
        "treatment": "Spray Chlorothalonil @ 2 g/L or Mancozeb @ 2.5 g/L. Remove lower infected leaves. Mulch to prevent splash.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 37,
        "label": "Tomato___Spider_mites",
        "crop": "tomato",
        "disease": "Spider Mites (Two-spotted)",
        "treatment": "Spray Dicofol 18.5 EC @ 2.5 ml/L or Abamectin @ 0.5 ml/L. Increase humidity. Release predatory mites (Phytoseiulus).",
        "severity_base": "MEDIUM",
    },
    {
        "index": 38,
        "label": "Tomato___Target_Spot",
        "crop": "tomato",
        "disease": "Target Spot",
        "treatment": "Spray Mancozeb @ 2.5 g/L or Azoxystrobin @ 1 ml/L. Remove plant debris after season.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 39,
        "label": "Tomato___Yellow_Leaf_Curl_Virus",
        "crop": "tomato",
        "disease": "Yellow Leaf Curl Virus",
        "treatment": "No cure for infected plants — remove and destroy. Control whitefly vector with Imidacloprid @ 0.5 ml/L. Use resistant varieties. Install yellow sticky traps.",
        "severity_base": "CRITICAL",
    },
    {
        "index": 40,
        "label": "Tomato___Mosaic_virus",
        "crop": "tomato",
        "disease": "Tomato Mosaic Virus",
        "treatment": "No chemical cure. Remove infected plants. Disinfect tools with 10% bleach. Use resistant varieties. Avoid tobacco products near plants.",
        "severity_base": "HIGH",
    },
    {
        "index": 41,
        "label": "Tomato___healthy",
        "crop": "tomato",
        "disease": "Healthy",
        "treatment": "No treatment needed. Continue regular scouting for whitefly and blight.",
        "severity_base": "LOW",
    },
    {
        "index": 42,
        "label": "Wheat___Brown_rust",
        "crop": "wheat",
        "disease": "Brown Rust (Leaf Rust)",
        "treatment": "Spray Propiconazole 25 EC @ 1 ml/L or Tebuconazole 250 EC @ 1 ml/L. Use resistant varieties.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 43,
        "label": "Wheat___Yellow_rust",
        "crop": "wheat",
        "disease": "Yellow Rust (Stripe Rust)",
        "treatment": "Spray Propiconazole 25 EC @ 1 ml/L immediately on detection. Repeat after 15 days. Use resistant varieties HD 3226, PBW 826.",
        "severity_base": "HIGH",
    },
    {
        "index": 44,
        "label": "Wheat___Septoria",
        "crop": "wheat",
        "disease": "Septoria Leaf Blotch",
        "treatment": "Spray Propiconazole 25 EC @ 1 ml/L or Tebuconazole @ 1 ml/L. Avoid excessive nitrogen.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 45,
        "label": "Wheat___healthy",
        "crop": "wheat",
        "disease": "Healthy",
        "treatment": "No treatment needed. Monitor for rust during Jan-Feb in cool humid conditions.",
        "severity_base": "LOW",
    },
    {
        "index": 46,
        "label": "Cotton___Bacterial_blight",
        "crop": "cotton",
        "disease": "Bacterial Blight (Angular Leaf Spot)",
        "treatment": "Spray Streptocycline @ 0.5 g/L + Copper oxychloride @ 3 g/L. Use acid-delinted and treated seed.",
        "severity_base": "MEDIUM",
    },
    {
        "index": 47,
        "label": "Cotton___Leaf_curl_virus",
        "crop": "cotton",
        "disease": "Cotton Leaf Curl Virus",
        "treatment": "No cure. Uproot and destroy infected plants. Control whitefly vector with Diafenthiuron 50 WP @ 1 g/L. Use tolerant varieties.",
        "severity_base": "CRITICAL",
    },
]

# Build lookup indices for fast access
_PLANTVILLAGE_BY_CROP: dict[str, list[int]] = defaultdict(list)
for _pv_cls in PLANTVILLAGE_CLASSES:
    _PLANTVILLAGE_BY_CROP[_pv_cls["crop"]].append(_pv_cls["index"])

_PLANTVILLAGE_CROP_NAMES: list[str] = sorted(
    set(c["crop"] for c in PLANTVILLAGE_CLASSES)
)

# Simulated AgMarkNet mandi data — base prices (Rs/quintal) by crop and region
_AGMARKNET_BASE_PRICES: dict[str, dict[str, float]] = {
    "wheat": {
        "north_india": 2425.0,
        "central_india": 2380.0,
        "south_india": 2500.0,
        "east_india": 2350.0,
    },
    "rice": {
        "north_india": 2300.0,
        "central_india": 2250.0,
        "south_india": 2100.0,
        "east_india": 2200.0,
    },
    "maize": {
        "north_india": 2090.0,
        "central_india": 2050.0,
        "south_india": 2150.0,
        "east_india": 1980.0,
    },
    "potato": {
        "north_india": 1200.0,
        "central_india": 1100.0,
        "south_india": 1350.0,
        "east_india": 1050.0,
    },
    "tomato": {
        "north_india": 2500.0,
        "central_india": 2200.0,
        "south_india": 1800.0,
        "east_india": 2000.0,
    },
    "cotton": {
        "north_india": 7521.0,
        "central_india": 7200.0,
        "south_india": 7400.0,
        "east_india": 7100.0,
    },
    "sugarcane": {
        "north_india": 380.0,
        "central_india": 340.0,
        "south_india": 350.0,
        "east_india": 330.0,
    },
    "mustard": {
        "north_india": 5950.0,
        "central_india": 5800.0,
        "south_india": 6100.0,
        "east_india": 5700.0,
    },
    "apple": {
        "north_india": 4500.0,
        "central_india": 4800.0,
        "south_india": 5200.0,
        "east_india": 4600.0,
    },
    "grape": {
        "north_india": 3500.0,
        "central_india": 3200.0,
        "south_india": 2800.0,
        "east_india": 3400.0,
    },
    "soybean": {
        "north_india": 4600.0,
        "central_india": 4300.0,
        "south_india": 4500.0,
        "east_india": 4200.0,
    },
    "orange": {
        "north_india": 3000.0,
        "central_india": 2800.0,
        "south_india": 2600.0,
        "east_india": 2900.0,
    },
}

# Simulated weather patterns by region
_WEATHER_PATTERNS: dict[str, dict[str, Any]] = {
    "north_india": {
        "temp_range": (5, 45),
        "humidity_range": (30, 90),
        "rain_prob_base": 0.3,
    },
    "central_india": {
        "temp_range": (10, 46),
        "humidity_range": (25, 85),
        "rain_prob_base": 0.25,
    },
    "south_india": {
        "temp_range": (18, 40),
        "humidity_range": (50, 95),
        "rain_prob_base": 0.4,
    },
    "east_india": {
        "temp_range": (8, 42),
        "humidity_range": (45, 95),
        "rain_prob_base": 0.45,
    },
}

# ============================================================
# Multi-Agent Pipeline: Pydantic Models
# ============================================================


class VisionRequest(BaseModel):
    """Request for the Vision Agent — crop disease classification."""

    image_base64: str | None = Field(
        None, description="Base64 encoded crop leaf image (optional for simulation)"
    )
    crop_type: str = Field(
        ..., description="Crop type, e.g. 'tomato', 'potato', 'wheat'"
    )
    symptoms: str | None = Field(
        None,
        description="Text description of visible symptoms for enhanced classification",
    )


class DiseaseClassification(BaseModel):
    class_index: int
    label: str
    disease_name: str
    confidence: float
    crop: str


class VisionResponse(BaseModel):
    status: str
    model_used: str
    crop_type: str
    top_prediction: DiseaseClassification
    top_5_predictions: list[DiseaseClassification]
    treatment: str
    all_38_classes_evaluated: bool
    timestamp: str


class VerifyRequest(BaseModel):
    """Request for the Verifier Agent — risk/severity assessment."""

    disease_name: str = Field(
        ..., description="Diagnosed disease name from Vision Agent"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score from Vision Agent"
    )
    crop_type: str = Field(..., description="Crop type")
    spread_percentage: float = Field(
        0.1, ge=0.0, le=1.0, description="Estimated percentage of field affected (0-1)"
    )
    days_since_onset: int = Field(
        3, ge=0, description="Approximate days since symptoms first noticed"
    )


class VerifyResponse(BaseModel):
    disease_name: str
    severity: str  # LOW / MEDIUM / HIGH / CRITICAL
    risk_score: float  # 0-100
    action: str  # MONITOR / TREAT / ESCALATE
    reasoning: list[str]
    recommended_actions: list[str]
    escalation_contact: str | None
    timestamp: str


class WeatherForecast(BaseModel):
    date: str
    temp_max_c: float
    temp_min_c: float
    humidity_pct: float
    rain_probability: float
    rain_mm: float
    wind_kph: float
    condition: str


class WeatherResponse(BaseModel):
    region: str
    lat: float | None
    lon: float | None
    crop_type: str
    forecast_days: int
    forecasts: list[WeatherForecast]
    irrigation_advice: str
    irrigation_reasoning: str
    timestamp: str


class MandiPrice(BaseModel):
    mandi_name: str
    district: str
    state: str
    price_per_quintal: float
    arrival_tonnes: float
    price_trend: str  # UP / DOWN / STABLE
    last_updated: str


class MarketResponse(BaseModel):
    crop_type: str
    region: str
    msp_reference: float | None
    mandi_prices: list[MandiPrice]
    best_selling_time: str
    price_recommendation: str
    timestamp: str


class MemoryLogRequest(BaseModel):
    """Request to log a farmer interaction."""

    farmer_id: str = Field(..., description="Unique farmer identifier")
    interaction_type: str = Field(
        ...,
        description="Type: disease_diagnosis, weather_check, market_query, general_chat",
    )
    crop_type: str | None = None
    disease_detected: str | None = None
    severity: str | None = None
    location: str | None = None
    notes: str | None = None


class FarmerInteraction(BaseModel):
    interaction_id: str
    timestamp: str
    interaction_type: str
    crop_type: str | None
    disease_detected: str | None
    severity: str | None
    location: str | None
    notes: str | None


class PatternAnalysis(BaseModel):
    total_interactions: int
    most_common_crop: str | None
    most_common_disease: str | None
    disease_frequency: dict[str, int]
    crop_frequency: dict[str, int]
    recurring_issues: list[str]
    risk_profile: str  # LOW_RISK / MODERATE_RISK / HIGH_RISK
    recommendation: str


class MemoryLogResponse(BaseModel):
    status: str
    farmer_id: str
    interaction_id: str
    total_interactions: int
    timestamp: str


class MemoryGetResponse(BaseModel):
    farmer_id: str
    total_interactions: int
    interactions: list[FarmerInteraction]
    pattern_analysis: PatternAnalysis
    timestamp: str


class LLMRequest(BaseModel):
    """Request for the LLM Agent — summary generation."""

    disease_info: dict[str, Any] | None = Field(
        None, description="Disease diagnosis context"
    )
    weather_info: dict[str, Any] | None = Field(
        None, description="Weather/irrigation context"
    )
    market_info: dict[str, Any] | None = Field(None, description="Market price context")
    farmer_query: str | None = Field(None, description="Farmer's original question")
    language: str = Field(
        "en", description="Target language: en, hi, pa, mr, ta, te, bn"
    )
    format_style: str = Field(
        "whatsapp", description="Output format: whatsapp, detailed, sms"
    )


class LLMResponse(BaseModel):
    summary: str
    language: str
    format_style: str
    model_used: str
    follow_up_suggestions: list[str]
    timestamp: str


class PipelineRequest(BaseModel):
    """Request for the full multi-agent pipeline."""

    farmer_id: str = Field(..., description="Farmer identifier for memory logging")
    crop_type: str = Field(..., description="Crop type, e.g. 'tomato', 'wheat'")
    image_base64: str | None = Field(None, description="Base64 crop photo (optional)")
    symptoms: str | None = Field(None, description="Visible symptom description")
    region: str = Field(
        "north_india",
        description="Region: north_india, central_india, south_india, east_india",
    )
    lat: float | None = Field(None, description="Latitude for weather")
    lon: float | None = Field(None, description="Longitude for weather")
    language: str = Field("en", description="Summary language")


class PipelineAgentResult(BaseModel):
    agent: str
    status: str
    data: dict[str, Any]


class PipelineResponse(BaseModel):
    farmer_id: str
    crop_type: str
    region: str
    pipeline_id: str
    agents_executed: list[str]
    vision_result: dict[str, Any]
    verification_result: dict[str, Any]
    weather_result: dict[str, Any]
    market_result: dict[str, Any]
    memory_result: dict[str, Any]
    llm_summary: dict[str, Any]
    full_summary: str
    timestamp: str


# ============================================================
# Multi-Agent Pipeline: Stores
# ============================================================

# DB: _farmer_memory -> FarmerInteractionRecord table

# ============================================================
# Multi-Agent Pipeline: Internal Agent Functions
# ============================================================


def _agent_vision(
    crop_type: str, symptoms: str | None = None, image_base64: str | None = None
) -> dict[str, Any]:
    """
    Vision Agent: Simulates MobileNetV2/ResNet classification on PlantVillage 38 classes.

    Uses numpy to produce realistic probability distributions. When symptoms or
    image_base64 are provided, they seed the RNG for deterministic-but-varied results.
    """
    crop_lower = crop_type.lower().strip()
    crop_lower = _CROP_ALIASES.get(crop_lower, crop_lower)

    # Build a deterministic seed from inputs for reproducibility
    seed_str = f"{crop_lower}:{symptoms or ''}:{(image_base64 or '')[:64]}"
    # Using random.seed instead of np.random.RandomState
    random.seed(seed_str)

    # Get class indices relevant to this crop
    crop_indices = _PLANTVILLAGE_BY_CROP.get(crop_lower, [])

    # If crop not in PlantVillage, find closest or use all
    if not crop_indices:
        # Map to closest PlantVillage crop or use all classes
        crop_indices = list(range(len(PLANTVILLAGE_CLASSES)))

    # Generate raw logits for ALL 48 classes (38 original + 10 extended)
    num_classes = len(PLANTVILLAGE_CLASSES)
    raw_logits = rng.normal(loc=0.0, scale=1.0, size=num_classes)

    # Boost logits for classes matching the input crop
    for idx in crop_indices:
        raw_logits[idx] += 3.0  # strong prior for matching crop

    # If symptoms hint at a specific disease, boost further
    if symptoms:
        symptoms_lower = symptoms.lower()
        for i, cls in enumerate(PLANTVILLAGE_CLASSES):
            disease_lower = cls["disease"].lower()
            label_lower = cls["label"].lower()
            # Check for keyword overlap between symptoms and disease name
            disease_words = set(disease_lower.replace("(", "").replace(")", "").split())
            symptom_words = set(symptoms_lower.split())
            overlap = disease_words & symptom_words
            if overlap:
                raw_logits[i] += 2.0 * len(overlap)
            # Check for common symptom-disease associations
            symptom_disease_map = {
                "yellow": ["rust", "curl", "mosaic", "greening"],
                "brown": ["blight", "rot", "spot", "rust"],
                "black": ["rot", "spot", "measles"],
                "white": ["mildew", "mold"],
                "spots": ["spot", "blight", "scorch"],
                "wilting": ["wilt", "blight", "virus"],
                "curling": ["curl", "virus"],
                "powdery": ["mildew"],
                "stripe": ["rust", "streak"],
                "lesion": ["spot", "blight", "blast"],
                "rot": ["rot"],
                "mold": ["mold", "mildew"],
            }
            for symptom_kw, disease_kws in symptom_disease_map.items():
                if symptom_kw in symptoms_lower:
                    for dkw in disease_kws:
                        if dkw in disease_lower or dkw in label_lower:
                            raw_logits[i] += 1.5

    # Healthy classes get a slight penalty if symptoms are described
    if symptoms and symptoms.strip():
        for i, cls in enumerate(PLANTVILLAGE_CLASSES):
            if cls["disease"] == "Healthy":
                raw_logits[i] -= 2.0
    else:
        # No symptoms → boost healthy classes
        for i, cls in enumerate(PLANTVILLAGE_CLASSES):
            if cls["disease"] == "Healthy" and cls["crop"] == crop_lower:
                raw_logits[i] += 2.5

    # Apply softmax to get probabilities
    # Logits boost logic remains same, just usage of rng replaced by random
    
    # Apply softmax to get probabilities (Pure Python)
    max_logit = max(raw_logits)
    exp_logits = [math.exp(l - max_logit) for l in raw_logits]
    sum_exp = sum(exp_logits)
    probabilities = [e / sum_exp for e in exp_logits]

    # Sort by probability descending
    # Create list of (index, prob) and sort
    indexed_probs = list(enumerate(probabilities))
    indexed_probs.sort(key=lambda x: x[1], reverse=True)
    sorted_indices = [x[0] for x in indexed_probs]

    top_5 = []
    for rank, idx in enumerate(sorted_indices[:5]):
        cls_info = PLANTVILLAGE_CLASSES[idx]
        top_5.append(
            DiseaseClassification(
                class_index=cls_info["index"],
                label=cls_info["label"],
                disease_name=cls_info["disease"],
                confidence=round(float(probabilities[idx]), 4),
                crop=cls_info["crop"],
            )
        )

    top_pred = top_5[0]
    top_cls_info = PLANTVILLAGE_CLASSES[top_pred.class_index]

    return {
        "status": "success",
        "model_used": "MobileNetV2-PlantVillage-Simulated (54K images, 38+ classes)",
        "crop_type": crop_lower,
        "top_prediction": top_pred.model_dump(),
        "top_5_predictions": [p.model_dump() for p in top_5],
        "treatment": top_cls_info["treatment"],
        "all_38_classes_evaluated": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _agent_verify(
    disease_name: str,
    confidence: float,
    crop_type: str,
    spread_percentage: float = 0.1,
    days_since_onset: int = 3,
) -> dict[str, Any]:
    """
    Verifier Agent: Evaluates risk/severity and decides action.
    Uses a multi-factor scoring system.
    """
    # Find the disease in PlantVillage classes
    base_severity = "MEDIUM"
    for cls in PLANTVILLAGE_CLASSES:
        if (
            cls["disease"].lower() == disease_name.lower()
            or cls["label"].lower() == disease_name.lower()
        ):
            base_severity = cls["severity_base"]
            break

    # Also check partial matches
    if base_severity == "MEDIUM":
        for cls in PLANTVILLAGE_CLASSES:
            if disease_name.lower() in cls["disease"].lower():
                base_severity = cls["severity_base"]
                break

    # Multi-factor risk score (0-100)
    severity_scores = {"LOW": 10, "MEDIUM": 40, "HIGH": 70, "CRITICAL": 90}
    base_score = severity_scores.get(base_severity, 40)

    # Factor 1: Confidence adjustment (-10 to +10)
    confidence_adj = (confidence - 0.5) * 20  # high confidence → higher risk score

    # Factor 2: Spread percentage (0-20)
    spread_adj = spread_percentage * 20

    # Factor 3: Days since onset (0-15)
    if days_since_onset <= 1:
        onset_adj = 0
    elif days_since_onset <= 3:
        onset_adj = 5
    elif days_since_onset <= 7:
        onset_adj = 10
    else:
        onset_adj = 15

    # Factor 4: Is disease known to be economically devastating?
    devastating_diseases = [
        "late blight",
        "neck blast",
        "citrus greening",
        "huanglongbing",
        "leaf curl virus",
        "yellow leaf curl",
        "esca",
        "black measles",
    ]
    devastation_adj = 0
    for dd in devastating_diseases:
        if dd in disease_name.lower():
            devastation_adj = 10
            break

    risk_score = min(
        100,
        max(0, base_score + confidence_adj + spread_adj + onset_adj + devastation_adj),
    )

    # Determine final severity from risk score
    if risk_score < 25:
        final_severity = "LOW"
    elif risk_score < 50:
        final_severity = "MEDIUM"
    elif risk_score < 75:
        final_severity = "HIGH"
    else:
        final_severity = "CRITICAL"

    # Determine action
    action_map = {
        "LOW": "MONITOR",
        "MEDIUM": "TREAT",
        "HIGH": "TREAT",
        "CRITICAL": "ESCALATE",
    }
    action = action_map[final_severity]

    # Build reasoning
    reasoning = []
    if disease_name.lower() == "healthy" or "healthy" in disease_name.lower():
        final_severity = "LOW"
        risk_score = 5.0
        action = "MONITOR"
        reasoning = [
            "Plant appears healthy",
            "No disease detected",
            "Continue regular monitoring",
        ]
    else:
        reasoning.append(f"Base severity for '{disease_name}': {base_severity}")
        reasoning.append(
            f"Classification confidence: {confidence:.1%} (adjustment: {confidence_adj:+.1f})"
        )
        reasoning.append(
            f"Estimated field spread: {spread_percentage:.0%} (adjustment: {spread_adj:+.1f})"
        )
        reasoning.append(
            f"Days since onset: {days_since_onset} (adjustment: {onset_adj:+.1f})"
        )
        if devastation_adj > 0:
            reasoning.append(
                f"Known economically devastating disease (+{devastation_adj})"
            )
        reasoning.append(f"Final risk score: {risk_score:.1f}/100 → {final_severity}")

    # Build recommended actions
    recommended_actions = []
    if action == "MONITOR":
        recommended_actions = [
            "Continue scouting every 3-5 days",
            "Take photos for comparison over time",
            "Maintain field hygiene and balanced nutrition",
        ]
    elif action == "TREAT":
        # Find treatment from PlantVillage
        treatment = "Apply recommended fungicide/pesticide as per diagnosis"
        for cls in PLANTVILLAGE_CLASSES:
            if cls["disease"].lower() == disease_name.lower():
                treatment = cls["treatment"]
                break
        recommended_actions = [
            treatment,
            "Apply treatment within 24-48 hours",
            "Scout again after 7 days to check effectiveness",
            "If spread continues, escalate to Krishi Vigyan Kendra",
        ]
    else:  # ESCALATE
        recommended_actions = [
            "Contact Krishi Vigyan Kendra (KVK) IMMEDIATELY",
            "Call agriculture helpline 1551 for expert guidance",
            "Isolate affected area — do not move plant material",
            "Take multiple photos from different angles for expert review",
            "Consider emergency fungicide/pesticide application while awaiting expert advice",
        ]

    escalation_contact = None
    if action == "ESCALATE":
        escalation_contact = (
            "Agriculture Helpline: 1551 | Nearest KVK | District Agriculture Officer"
        )

    return {
        "disease_name": disease_name,
        "severity": final_severity,
        "risk_score": round(risk_score, 1),
        "action": action,
        "reasoning": reasoning,
        "recommended_actions": recommended_actions,
        "escalation_contact": escalation_contact,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _agent_weather(
    region: str, crop_type: str, lat: float | None = None, lon: float | None = None
) -> dict[str, Any]:
    """
    Weather Agent: Simulates short-term forecast and provides irrigation advice.
    Uses numpy for realistic weather simulation based on region and season.
    """
    region_lower = region.lower().strip()
    if region_lower not in _WEATHER_PATTERNS:
        region_lower = "north_india"

    pattern = _WEATHER_PATTERNS[region_lower]
    now = datetime.now(timezone.utc)

    # Deterministic seed from date + region for consistent daily forecasts
    seed_str = f"{now.strftime('%Y-%m-%d')}:{region_lower}:{crop_type}"
    random.seed(seed_str)

    # Season-based adjustments
    month = now.month
    if month in (6, 7, 8, 9):  # monsoon
        rain_mult = 2.5
        temp_adj = -2
    elif month in (12, 1, 2):  # winter
        rain_mult = 0.3
        temp_adj = -8
    elif month in (3, 4, 5):  # summer
        rain_mult = 0.5
        temp_adj = 5
    else:  # post-monsoon
        rain_mult = 0.8
        temp_adj = 0

    forecasts = []
    rain_tomorrow = False

    for day_offset in range(5):
        # Use random instead of np.random.RandomState
        # For simplicity, we just use random.gauss for normal distributions
        temp_min = pattern["temp_range"][0] + temp_adj + random.gauss(0, 3)
        temp_max = pattern["temp_range"][1] + temp_adj + random.gauss(0, 3)
        temp_min = round(max(temp_min, -5), 1)
        temp_max = round(min(max(temp_max, temp_min + 3), 50), 1)

        avg_humidity = (pattern["humidity_range"][0] + pattern["humidity_range"][1]) / 2
        humidity = random.gauss(avg_humidity, 15)
        humidity = round(min(max(humidity, pattern["humidity_range"][0]), pattern["humidity_range"][1]), 1)

        rain_prob = pattern["rain_prob_base"] * rain_mult + random.gauss(0, 0.15)
        rain_prob = round(min(max(rain_prob, 0.0), 0.95), 2)

        rain_mm = 0.0
        if rain_prob > 0.4:
            # exponential approximation: -scale * log(1 - u)
            rain_mm = round(- (rain_prob * 20) * math.log(1 - random.random()), 1)
        elif rain_prob > 0.2:
            rain_mm = round(- (rain_prob * 5) * math.log(1 - random.random()), 1)

        wind_kph = round(min(max(random.gauss(12, 8), 0), 60), 1)

        # Determine condition string
        if rain_mm > 20:
            condition = "Heavy Rain"
        elif rain_mm > 5:
            condition = "Moderate Rain"
        elif rain_mm > 0.5:
            condition = "Light Rain"
        elif humidity > 80:
            condition = "Cloudy/Overcast"
        elif temp_max > 40:
            condition = "Hot & Sunny"
        elif temp_min < 5:
            condition = "Cold/Frost Risk"
        else:
            condition = "Clear/Partly Cloudy"

        forecast_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        forecast_date = forecast_date + timedelta(days=day_offset)

        if day_offset == 1 and rain_prob > 0.35:
            rain_tomorrow = True

        forecasts.append(
            WeatherForecast(
                date=forecast_date.strftime("%Y-%m-%d"),
                temp_max_c=temp_max,
                temp_min_c=temp_min,
                humidity_pct=humidity,
                rain_probability=rain_prob,
                rain_mm=rain_mm,
                wind_kph=wind_kph,
                condition=condition,
            )
        )

    # Irrigation advice logic
    crop_lower = _CROP_ALIASES.get(crop_type.lower(), crop_type.lower())
    today_rain = forecasts[0].rain_mm if forecasts else 0
    today_rain_prob = forecasts[0].rain_probability if forecasts else 0

    if rain_tomorrow and today_rain < 5:
        irrigation_advice = "Skip irrigation — Rain expected tomorrow"
        irrigation_reasoning = (
            f"Tomorrow's rain probability is {forecasts[1].rain_probability:.0%} with "
            f"expected {forecasts[1].rain_mm:.1f} mm. Save water and irrigate only if "
            f"rain does not materialize."
        )
    elif today_rain > 10:
        irrigation_advice = "Skip irrigation — Sufficient rain today"
        irrigation_reasoning = (
            f"Today received {today_rain:.1f} mm of rain which is adequate. "
            f"Check soil moisture tomorrow before deciding."
        )
    elif today_rain_prob > 0.6:
        irrigation_advice = "Skip irrigation — High chance of rain today"
        irrigation_reasoning = (
            f"Rain probability today is {today_rain_prob:.0%}. Wait until evening "
            f"and irrigate only if rain does not occur."
        )
    elif forecasts[0].temp_max_c > 40:
        irrigation_advice = "Irrigate today — Hot conditions detected"
        irrigation_reasoning = (
            f"Temperature expected to reach {forecasts[0].temp_max_c:.1f}°C. "
            f"Crops face heat stress. Irrigate preferably in early morning or late evening."
        )
    elif forecasts[0].condition == "Cold/Frost Risk":
        irrigation_advice = "Light irrigation recommended — Frost protection"
        irrigation_reasoning = (
            f"Minimum temperature {forecasts[0].temp_min_c:.1f}°C indicates frost risk. "
            f"Light irrigation in the evening can protect crops from frost damage."
        )
    else:
        irrigation_advice = "Irrigate today if scheduled"
        irrigation_reasoning = (
            f"No significant rain expected in next 48 hours. "
            f"Follow your crop's irrigation schedule. "
            f"Current conditions: {forecasts[0].condition}, {forecasts[0].humidity_pct:.0f}% humidity."
        )

    return {
        "region": region_lower,
        "lat": lat,
        "lon": lon,
        "crop_type": crop_lower,
        "forecast_days": 5,
        "forecasts": [f.model_dump() for f in forecasts],
        "irrigation_advice": irrigation_advice,
        "irrigation_reasoning": irrigation_reasoning,
        "timestamp": now.isoformat(),
    }


def _agent_market(crop_type: str, region: str) -> dict[str, Any]:
    """
    Market Agent: Simulates AgMarkNet mandi data and recommends best selling time.
    Uses numpy for realistic price variation across mandis.
    """
    crop_lower = _CROP_ALIASES.get(crop_type.lower(), crop_type.lower())
    region_lower = region.lower().strip()
    now = datetime.now(timezone.utc)

    # Get base price
    crop_prices = _AGMARKNET_BASE_PRICES.get(crop_lower, {})
    base_price = crop_prices.get(region_lower, crop_prices.get("north_india", 2000.0))

    # Deterministic seed for consistent daily prices
    seed_str = f"{now.strftime('%Y-%m-%d')}:{crop_lower}:{region_lower}"
    seed_val = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    rng = np.random.RandomState(seed_val)

    # MSP reference
    msp_data = FARMING_KNOWLEDGE.get("market_info", {}).get(crop_lower, {})
    msp_ref = None
    for key in ("msp_2025_26", "frp_2025_26"):
        val = msp_data.get(key, "")
        if val:
            # Extract numeric value from string like "Rs 2,425 per quintal"
            nums = re.findall(r"[\d,]+", val.replace(",", ""))
            if nums:
                try:
                    msp_ref = float(nums[0].replace(",", ""))
                except ValueError:
                    logger.warning(f"Failed to parse MSP value: {nums[0]}")
                    pass

            break

    # Simulated mandi names per region
    mandi_names_by_region: dict[str, list[dict[str, str]]] = {
        "north_india": [
            {"name": "Azadpur Mandi", "district": "Delhi", "state": "Delhi"},
            {
                "name": "Ludhiana Grain Market",
                "district": "Ludhiana",
                "state": "Punjab",
            },
            {"name": "Karnal Mandi", "district": "Karnal", "state": "Haryana"},
            {"name": "Hapur Mandi", "district": "Hapur", "state": "Uttar Pradesh"},
            {"name": "Jaipur Mandi", "district": "Jaipur", "state": "Rajasthan"},
        ],
        "central_india": [
            {"name": "Indore Mandi", "district": "Indore", "state": "Madhya Pradesh"},
            {"name": "Nagpur APMC", "district": "Nagpur", "state": "Maharashtra"},
            {"name": "Bhopal Mandi", "district": "Bhopal", "state": "Madhya Pradesh"},
            {"name": "Raipur Mandi", "district": "Raipur", "state": "Chhattisgarh"},
        ],
        "south_india": [
            {"name": "Koyambedu Market", "district": "Chennai", "state": "Tamil Nadu"},
            {"name": "Vashi APMC", "district": "Navi Mumbai", "state": "Maharashtra"},
            {
                "name": "Yeshwanthpur APMC",
                "district": "Bengaluru",
                "state": "Karnataka",
            },
            {
                "name": "Madanapalle Market",
                "district": "Annamayya",
                "state": "Andhra Pradesh",
            },
        ],
        "east_india": [
            {"name": "Burdwan Mandi", "district": "Burdwan", "state": "West Bengal"},
            {"name": "Patna Mandi", "district": "Patna", "state": "Bihar"},
            {"name": "Cuttack Mandi", "district": "Cuttack", "state": "Odisha"},
            {"name": "Ranchi Market", "district": "Ranchi", "state": "Jharkhand"},
        ],
    }

    mandis_info = mandi_names_by_region.get(
        region_lower, mandi_names_by_region["north_india"]
    )

    mandi_prices = []
    best_price = 0.0
    best_mandi = ""

    for mandi_info in mandis_info:
        # Each mandi has its own price variation
        price_variation = rng.normal(0, base_price * 0.08)  # ~8% std dev
        price = round(max(base_price * 0.7, base_price + price_variation), 2)

        arrival = round(float(rng.exponential(scale=50) + 10), 1)

        trend_roll = rng.random()
        if trend_roll < 0.35:
            trend = "UP"
        elif trend_roll < 0.65:
            trend = "STABLE"
        else:
            trend = "DOWN"

        if price > best_price:
            best_price = price
            best_mandi = mandi_info["name"]

        mandi_prices.append(
            MandiPrice(
                mandi_name=mandi_info["name"],
                district=mandi_info["district"],
                state=mandi_info["state"],
                price_per_quintal=price,
                arrival_tonnes=arrival,
                price_trend=trend,
                last_updated=now.strftime("%Y-%m-%d"),
            )
        )

    # Sort by price descending
    mandi_prices.sort(key=lambda x: x.price_per_quintal, reverse=True)

    # Price recommendation
    up_count = sum(1 for m in mandi_prices if m.price_trend == "UP")
    down_count = sum(1 for m in mandi_prices if m.price_trend == "DOWN")

    if up_count > down_count:
        best_selling_time = "Wait 3-5 days — prices are trending upward"
        price_recommendation = (
            f"Prices trending UP in {up_count}/{len(mandi_prices)} mandis. "
            f"Consider holding stock for better returns. Best current price: Rs {best_price:.0f}/qtl at {best_mandi}."
        )
    elif down_count > up_count:
        best_selling_time = "Sell now — prices are trending downward"
        price_recommendation = (
            f"Prices trending DOWN in {down_count}/{len(mandi_prices)} mandis. "
            f"Sell at the earliest to avoid losses. Best current price: Rs {best_price:.0f}/qtl at {best_mandi}."
        )
    else:
        best_selling_time = "Prices stable — sell at your convenience"
        price_recommendation = (
            f"Prices are relatively STABLE. "
            f"Best current price: Rs {best_price:.0f}/qtl at {best_mandi}. "
            f"Compare with MSP if available and sell where you get better return."
        )

    if msp_ref and best_price < msp_ref:
        price_recommendation += (
            f" Note: MSP is Rs {msp_ref:.0f}/qtl which is higher than current best market price. "
            f"Register for government procurement to sell at MSP."
        )

    return {
        "crop_type": crop_lower,
        "region": region_lower,
        "msp_reference": msp_ref,
        "mandi_prices": [m.model_dump() for m in mandi_prices],
        "best_selling_time": best_selling_time,
        "price_recommendation": price_recommendation,
        "timestamp": now.isoformat(),
    }


async def _agent_memory_log(
    farmer_id: str,
    interaction_type: str,
    crop_type: str | None = None,
    disease_detected: str | None = None,
    severity: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """
    Memory Agent (Log): Logs a farmer interaction to the database.
    """
    if db is None:
        raise ValueError("db session is required")
    interaction_id = f"int-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    db.add(
        FarmerInteractionRecord(
            farmer_id=farmer_id,
            interaction_id=interaction_id,
            interaction_type=interaction_type,
            crop_type=crop_type,
            disease_detected=disease_detected,
            severity=severity,
            location=location,
            notes=notes,
            timestamp=now.isoformat(),
        )
    )
    await db.flush()

    total_result = await db.execute(
        select(sa_func.count())
        .select_from(FarmerInteractionRecord)
        .where(FarmerInteractionRecord.farmer_id == farmer_id)
    )
    total_interactions = int(total_result.scalar() or 0)

    return {
        "status": "logged",
        "farmer_id": farmer_id,
        "interaction_id": interaction_id,
        "total_interactions": total_interactions,
        "timestamp": now.isoformat(),
    }


async def _agent_memory_get(
    farmer_id: str, db: AsyncSession | None = None
) -> dict[str, Any]:
    """
    Memory Agent (Get): Retrieves farmer history and performs pattern analysis.
    """
    if db is None:
        raise ValueError("db session is required")
    now = datetime.now(timezone.utc)
    interactions_result = await db.execute(
        select(FarmerInteractionRecord)
        .where(FarmerInteractionRecord.farmer_id == farmer_id)
        .order_by(FarmerInteractionRecord.id)
    )
    interactions = [
        interaction.to_dict() for interaction in interactions_result.scalars().all()
    ]

    # Pattern analysis
    disease_freq: dict[str, int] = defaultdict(int)
    crop_freq: dict[str, int] = defaultdict(int)
    severity_counts: dict[str, int] = defaultdict(int)

    for inter in interactions:
        if inter.get("disease_detected"):
            disease_freq[inter["disease_detected"]] += 1
        if inter.get("crop_type"):
            crop_freq[inter["crop_type"]] += 1
        if inter.get("severity"):
            severity_counts[inter["severity"]] += 1

    most_common_crop = (
        max(crop_freq, key=lambda key: crop_freq[key]) if crop_freq else None
    )
    most_common_disease = (
        max(disease_freq, key=lambda key: disease_freq[key]) if disease_freq else None
    )

    # Detect recurring issues
    recurring_issues = []
    for disease, count in disease_freq.items():
        if count >= 2:
            recurring_issues.append(
                f"'{disease}' detected {count} times — possible recurring/endemic issue"
            )

    for crop, count in crop_freq.items():
        if count >= 3 and crop in disease_freq:
            recurring_issues.append(
                f"Frequent disease issues with '{crop}' crop — consider resistant varieties or crop rotation"
            )

    # Risk profile
    critical_count = severity_counts.get("CRITICAL", 0)
    high_count = severity_counts.get("HIGH", 0)
    if critical_count >= 2 or (critical_count >= 1 and high_count >= 2):
        risk_profile = "HIGH_RISK"
        recommendation = (
            "Your farm has experienced multiple severe disease incidents. "
            "Strongly recommend: (1) Soil health testing, (2) Crop rotation, "
            "(3) Resistant variety adoption, (4) Regular KVK consultation."
        )
    elif high_count >= 2 or len(recurring_issues) >= 2:
        risk_profile = "MODERATE_RISK"
        recommendation = (
            "Some recurring disease patterns detected. "
            "Recommend: (1) Preventive fungicide schedule, (2) Improved field hygiene, "
            "(3) Consider switching to resistant varieties."
        )
    else:
        risk_profile = "LOW_RISK"
        recommendation = (
            "Farm health appears manageable. Continue regular scouting "
            "and maintain balanced fertilization for best disease resistance."
        )

    pattern_analysis = {
        "total_interactions": len(interactions),
        "most_common_crop": most_common_crop,
        "most_common_disease": most_common_disease,
        "disease_frequency": dict(disease_freq),
        "crop_frequency": dict(crop_freq),
        "recurring_issues": recurring_issues,
        "risk_profile": risk_profile,
        "recommendation": recommendation,
    }

    return {
        "farmer_id": farmer_id,
        "total_interactions": len(interactions),
        "interactions": interactions,
        "pattern_analysis": pattern_analysis,
        "timestamp": now.isoformat(),
    }


async def _agent_llm(
    disease_info: dict[str, Any] | None = None,
    weather_info: dict[str, Any] | None = None,
    market_info: dict[str, Any] | None = None,
    farmer_query: str | None = None,
    language: str = "en",
    format_style: str = "whatsapp",
) -> dict[str, Any]:
    """
    LLM Agent: Generates a comprehensive advisory using NVIDIA NIM.
    Falls back to template-based generation if NVIDIA is unavailable.
    """
    now = datetime.now(timezone.utc)

    # --- Try NVIDIA-enhanced summary first ---
    if _NVIDIA_AVAILABLE:
        context_parts: list[str] = []
        if disease_info:
            top = disease_info.get("top_prediction", {})
            context_parts.append(
                f"Disease diagnosis: {top.get('disease_name', 'Unknown')} "
                f"({top.get('confidence', 0):.0%} confidence) on {disease_info.get('crop_type', 'crop')}. "
                f"Treatment: {disease_info.get('treatment', 'N/A')}."
            )
        if weather_info:
            forecasts = weather_info.get("forecasts", [])
            today = forecasts[0] if forecasts else {}
            context_parts.append(
                f"Weather: {today.get('condition', 'N/A')}, "
                f"{today.get('temp_max_c', 'N/A')}°C/{today.get('temp_min_c', 'N/A')}°C, "
                f"rain {today.get('rain_probability', 0):.0%}. "
                f"Irrigation advice: {weather_info.get('irrigation_advice', 'N/A')}."
            )
        if market_info:
            prices = market_info.get("mandi_prices", [])
            best = prices[0] if prices else {}
            context_parts.append(
                f"Market: best Rs {best.get('price_per_quintal', 'N/A')}/qtl at "
                f"{best.get('mandi_name', 'N/A')} ({best.get('price_trend', 'N/A')} trend). "
                f"Advice: {market_info.get('best_selling_time', 'N/A')}."
            )

        llm_prompt = (
            farmer_query or "Provide a comprehensive advisory based on the data."
        )
        if format_style == "whatsapp":
            llm_prompt += "\n\nFormat as a WhatsApp-friendly message with bold headers and emojis."
        elif format_style == "sms":
            llm_prompt += "\n\nKeep it very brief (≤160 chars) like an SMS."

        nvidia_text = await _call_nvidia(
            user_message=llm_prompt,
            kb_context="\n".join(context_parts),
            history=[],
            language=language,
        )
        if nvidia_text:
            # Build follow-ups from context
            follow_ups: list[str] = []
            if disease_info:
                dname = disease_info.get("top_prediction", {}).get("disease_name", "")
                if "healthy" not in dname.lower():
                    follow_ups.append(
                        "Should I check treatment availability at nearby shops?"
                    )
                    follow_ups.append("Do you want a detailed spray schedule?")
            if weather_info:
                follow_ups.append("Want a 5-day detailed forecast?")
            if market_info:
                follow_ups.append("Should I track price trends for the next week?")
            if not follow_ups:
                follow_ups = [
                    "Ask me anything about your crop!",
                    "Want fertilizer or irrigation advice?",
                ]

            return {
                "summary": nvidia_text,
                "language": language,
                "format_style": format_style,
                "model_used": "NVIDIA-Llama-3.3",
                "follow_up_suggestions": follow_ups,
                "timestamp": now.isoformat(),
            }

    # --- Fallback: template-based summary (original logic) ---
    return _agent_llm_template(
        disease_info=disease_info,
        weather_info=weather_info,
        market_info=market_info,
        language=language,
        format_style=format_style,
    )


def _agent_llm_template(
    disease_info: dict[str, Any] | None = None,
    weather_info: dict[str, Any] | None = None,
    market_info: dict[str, Any] | None = None,
    language: str = "en",
    format_style: str = "whatsapp",
) -> dict[str, Any]:
    """Template-based fallback for _agent_llm when NVIDIA is unavailable."""
    now = datetime.now(timezone.utc)
    sections = []

    # Language greetings and headers
    lang_config: dict[str, dict[str, str]] = {
        "en": {
            "greeting": "Namaste Kisaan!",
            "disease_hdr": "Disease Alert",
            "weather_hdr": "Weather & Irrigation",
            "market_hdr": "Market Update",
            "footer": "For expert help, call 1551.",
        },
        "hi": {
            "greeting": "नमस्ते किसान!",
            "disease_hdr": "रो�- चेतावनी",
            "weather_hdr": "मौसम और सिंचाई",
            "market_hdr": "बाज़ार अपडेट",
            "footer": "विशेषज्ञ सहायता के लिए 1551 पर कॉल करें।",
        },
        "pa": {
            "greeting": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਕਿਸਾਨ!",
            "disease_hdr": "ਬਿਮਾਰੀ ਚੇਤਾਵਨੀ",
            "weather_hdr": "ਮੌਸਮ ਅਤੇ ਸਿੰਚਾਈ",
            "market_hdr": "ਮੰਡੀ ਅੱਪਡੇਟ",
            "footer": "ਮਾਹਿਰ ਮਦਦ ਲਈ 1551 ਤੇ ਕਾਲ ਕਰੋ।",
        },
        "mr": {
            "greeting": "नमस्कार शेतकरी!",
            "disease_hdr": "रो�- इशारा",
            "weather_hdr": "हवामान आणि सिंचन",
            "market_hdr": "बाजार भाव",
            "footer": "तज्ञ मदतीसाठी 1551 वर कॉल करा।",
        },
        "ta": {
            "greeting": "வணக்கம் விவசாயி!",
            "disease_hdr": "நோய் எச்சரிக்கை",
            "weather_hdr": "வானிலை & நீர்ப்பாசனம்",
            "market_hdr": "சந்தை புதுப்பிப்பு",
            "footer": "நிபுணர் உதவிக்கு 1551 அழைக்கவும்.",
        },
        "te": {
            "greeting": "నమస్కారం రైతు!",
            "disease_hdr": "వ్యాధి హెచ్చరిక",
            "weather_hdr": "వాతావరణం & నీటిపారుదల",
            "market_hdr": "మార్కెట్ అప్‌డేట్",
            "footer": "నిపుణుల సహాయం కోసం 1551 కి కాల్ చేయండి.",
        },
        "bn": {
            "greeting": "নমস্কার কৃষক!",
            "disease_hdr": "রো�- সতর্কতা",
            "weather_hdr": "আবহাওয়া ও সেচ",
            "market_hdr": "বাজার আপডেট",
            "footer": "বিশেষজ্ঞ সাহায্যের জন্য 1551 কল করুন।",
        },
    }

    lc = lang_config.get(language, lang_config["en"])

    if format_style == "whatsapp":
        sep = "\n─────────────────\n"
    elif format_style == "sms":
        sep = " | "
    else:
        sep = "\n\n"

    # Greeting
    sections.append(lc["greeting"])

    # Disease section
    if disease_info:
        disease_name = disease_info.get("top_prediction", {}).get(
            "disease_name", "Unknown"
        )
        confidence = disease_info.get("top_prediction", {}).get("confidence", 0)
        treatment = disease_info.get("treatment", "Consult KVK for treatment.")
        crop = disease_info.get("crop_type", "")

        if format_style == "sms":
            sections.append(
                f"{lc['disease_hdr']}: {disease_name} ({confidence:.0%}) on {crop}. {treatment}"
            )
        else:
            sections.append(f"*{lc['disease_hdr']}*")
            sections.append(f"Crop: {crop.title()}")
            sections.append(f"Disease: {disease_name}")
            sections.append(f"Confidence: {confidence:.1%}")
            sections.append(f"Treatment: {treatment}")

    # Weather section
    if weather_info:
        irrigation = weather_info.get("irrigation_advice", "Check soil moisture")
        forecasts = weather_info.get("forecasts", [])
        today = forecasts[0] if forecasts else {}

        if format_style == "sms":
            sections.append(
                f"{lc['weather_hdr']}: {irrigation}. Today {today.get('condition', 'N/A')}, {today.get('temp_max_c', 'N/A')}C"
            )
        else:
            sections.append(sep)
            sections.append(f"*{lc['weather_hdr']}*")
            if today:
                sections.append(
                    f"Today: {today.get('condition', 'N/A')}, {today.get('temp_max_c', 'N/A')}°C / {today.get('temp_min_c', 'N/A')}°C"
                )
                sections.append(f"Rain chance: {today.get('rain_probability', 0):.0%}")
            sections.append(f"Advice: {irrigation}")

    # Market section
    if market_info:
        best_time = market_info.get("best_selling_time", "Check mandi rates")
        prices = market_info.get("mandi_prices", [])
        best = prices[0] if prices else {}

        if format_style == "sms":
            sections.append(
                f"{lc['market_hdr']}: Best Rs {best.get('price_per_quintal', 'N/A')}/qtl at {best.get('mandi_name', 'N/A')}. {best_time}"
            )
        else:
            sections.append(sep)
            sections.append(f"*{lc['market_hdr']}*")
            if best:
                sections.append(
                    f"Best Price: Rs {best.get('price_per_quintal', 'N/A')}/qtl"
                )
                sections.append(f"Mandi: {best.get('mandi_name', 'N/A')}")
                sections.append(f"Trend: {best.get('price_trend', 'N/A')}")
            sections.append(f"Advice: {best_time}")

    # Footer
    sections.append(sep if format_style != "sms" else " | ")
    sections.append(lc["footer"])

    if format_style == "sms":
        summary = " | ".join(s for s in sections if s.strip() and s != " | ")
    else:
        summary = "\n".join(sections)

    # Follow-up suggestions
    follow_ups = []
    if disease_info:
        disease_name = disease_info.get("top_prediction", {}).get("disease_name", "")
        if "healthy" not in disease_name.lower():
            follow_ups.append("Should I check treatment availability at nearby shops?")
            follow_ups.append("Do you want a detailed spray schedule?")
    if weather_info:
        follow_ups.append("Want a 5-day detailed forecast?")
    if market_info:
        follow_ups.append("Should I track price trends for the next week?")
        follow_ups.append("Do you want directions to the best-price mandi?")
    if not follow_ups:
        follow_ups = [
            "Ask me anything about your crop!",
            "Want fertilizer or irrigation advice?",
        ]

    return {
        "summary": summary,
        "language": language,
        "format_style": format_style,
        "model_used": "Template-Fallback",
        "follow_up_suggestions": follow_ups,
        "timestamp": now.isoformat(),
    }


# ============================================================
# Multi-Agent Pipeline: API Endpoints
# ============================================================


@app.post("/agent/vision", response_model=VisionResponse)
async def agent_vision(request: VisionRequest):
    """
    Vision Agent: Classify crop disease from image/symptoms using simulated
    MobileNetV2/ResNet trained on PlantVillage dataset (54K images, 38 classes).
    """
    result = _agent_vision(
        crop_type=request.crop_type,
        symptoms=request.symptoms,
        image_base64=request.image_base64,
    )
    return VisionResponse(**result)


@app.post("/agent/verify", response_model=VerifyResponse)
async def agent_verify(request: VerifyRequest):
    """
    Verifier Agent: Evaluate risk/severity level and decide action
    (MONITOR / TREAT / ESCALATE).
    """
    result = _agent_verify(
        disease_name=request.disease_name,
        confidence=request.confidence,
        crop_type=request.crop_type,
        spread_percentage=request.spread_percentage,
        days_since_onset=request.days_since_onset,
    )
    return VerifyResponse(**result)


@app.get("/agent/weather", response_model=WeatherResponse)
async def agent_weather(
    region: str = Query(
        "north_india",
        description="Region: north_india, central_india, south_india, east_india",
    ),
    crop_type: str = Query("wheat", description="Crop type for irrigation advice"),
    lat: float | None = Query(None, description="Latitude (optional)"),
    lon: float | None = Query(None, description="Longitude (optional)"),
):
    """
    Weather Agent: Short-term forecast with irrigation advice.
    """
    result = _agent_weather(
        region=region,
        crop_type=crop_type,
        lat=lat,
        lon=lon,
    )
    return WeatherResponse(**result)


@app.get("/agent/market", response_model=MarketResponse)
async def agent_market(
    crop_type: str = Query("wheat", description="Crop type for price data"),
    region: str = Query(
        "north_india",
        description="Region: north_india, central_india, south_india, east_india",
    ),
):
    """
    Market Agent: Nearby mandi prices from simulated AgMarkNet data
    with best selling time recommendation.
    """
    result = _agent_market(crop_type=crop_type, region=region)
    return MarketResponse(**result)


@app.post("/agent/memory/log", response_model=MemoryLogResponse)
async def agent_memory_log(
    request: MemoryLogRequest, db: AsyncSession = Depends(get_db)
):
    """
    Memory Agent (Log): Record a farmer interaction for profile building
    and pattern analysis.
    """
    result = await _agent_memory_log(
        farmer_id=request.farmer_id,
        interaction_type=request.interaction_type,
        crop_type=request.crop_type,
        disease_detected=request.disease_detected,
        severity=request.severity,
        location=request.location,
        notes=request.notes,
        db=db,
    )
    return MemoryLogResponse(**result)


@app.get("/agent/memory/{farmer_id}", response_model=MemoryGetResponse)
async def agent_memory_get(farmer_id: str, db: AsyncSession = Depends(get_db)):
    """
    Memory Agent (Get): Retrieve farmer interaction history and pattern analysis.
    """
    result = await _agent_memory_get(farmer_id=farmer_id, db=db)
    return MemoryGetResponse(**result)


@app.post("/agent/llm", response_model=LLMResponse)
async def agent_llm(request: LLMRequest):
    """
    LLM Agent: Generate WhatsApp-style summaries in local language
    using NVIDIA NIM (with template fallback).
    """
    result = await _agent_llm(
        disease_info=request.disease_info,
        weather_info=request.weather_info,
        market_info=request.market_info,
        farmer_query=request.farmer_query,
        language=request.language,
        format_style=request.format_style,
    )
    return LLMResponse(**result)


@app.post("/pipeline/analyze", response_model=PipelineResponse)
async def pipeline_analyze(
    request: PipelineRequest, db: AsyncSession = Depends(get_db)
):
    """
    Full Multi-Agent Pipeline: The crown jewel.

    Takes crop photo metadata + location, orchestrates ALL agents in sequence:
    Vision → Verifier → Weather → Market → Memory → LLM Summary
    Returns comprehensive advisory in a single response.
    """
    pipeline_id = f"pipe-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # 1. Vision Agent — disease classification
    vision_result = _agent_vision(
        crop_type=request.crop_type,
        symptoms=request.symptoms,
        image_base64=request.image_base64,
    )

    # Extract top prediction for downstream agents
    top_pred = vision_result.get("top_prediction", {})
    disease_name = top_pred.get("disease_name", "Unknown")
    confidence = top_pred.get("confidence", 0.0)

    # 2. Verifier Agent — risk assessment
    verify_result = _agent_verify(
        disease_name=disease_name,
        confidence=confidence,
        crop_type=request.crop_type,
    )

    # 3. Weather Agent — forecast + irrigation
    weather_result = _agent_weather(
        region=request.region,
        crop_type=request.crop_type,
        lat=request.lat,
        lon=request.lon,
    )

    # 4. Market Agent — mandi prices
    market_result = _agent_market(
        crop_type=request.crop_type,
        region=request.region,
    )

    # 5. Memory Agent — log this interaction
    memory_result = await _agent_memory_log(
        farmer_id=request.farmer_id,
        interaction_type="pipeline_analysis",
        crop_type=request.crop_type,
        disease_detected=disease_name,
        severity=verify_result.get("severity"),
        location=request.region,
        notes=f"Pipeline {pipeline_id}: {disease_name} ({confidence:.1%})",
        db=db,
    )

    # 6. LLM Agent — generate comprehensive summary
    llm_result = await _agent_llm(
        disease_info=vision_result,
        weather_info=weather_result,
        market_info=market_result,
        farmer_query=request.symptoms,
        language=request.language,
        format_style="whatsapp",
    )

    return PipelineResponse(
        farmer_id=request.farmer_id,
        crop_type=request.crop_type,
        region=request.region,
        pipeline_id=pipeline_id,
        agents_executed=["vision", "verifier", "weather", "market", "memory", "llm"],
        vision_result=vision_result,
        verification_result=verify_result,
        weather_result=weather_result,
        market_result=market_result,
        memory_result=memory_result,
        llm_summary=llm_result,
        full_summary=llm_result.get("summary", ""),
        timestamp=now.isoformat(),
    )


if __name__ == "__main__":
    uvicorn.run(
        "services.kisaan_sahayak.app:app", host="0.0.0.0", port=8006, reload=True
    )
