"""Fasal Rakshak - Crop protection and disease detection service."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
import uuid

import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.shared.auth.router import router as auth_router, setup_rate_limiting
from services.shared.config import settings
from services.shared.db.session import close_db, init_db, get_db
from services.shared.db.models import DiseaseDetection

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# Knowledge Base
# ============================================================

CROP_DISEASES: dict[str, list[dict]] = {
    "wheat": [
        {
            "name": "Leaf Rust",
            "scientific_name": "Puccinia triticina",
            "symptoms": [
                "orange pustules on leaves",
                "yellowing of leaves",
                "small round orange spots",
                "reduced grain filling",
            ],
            "severity_factors": {"temperature_range": (15, 25), "humidity_min": 70},
            "favorable_months": [1, 2, 3, 11, 12],
            "growth_stages": ["vegetative", "flowering", "maturity"],
            "treatment": {
                "chemical": "Propiconazole 25% EC @ 0.1% (1 mL/L water), spray at first appearance",
                "organic": "Neem oil spray at 5 mL/L water; remove and destroy infected leaves",
                "preventive": "Use resistant varieties (HD-3226, DBW-187); avoid late sowing; balanced N fertilization",
            },
            "season": ["rabi"],
        },
        {
            "name": "Powdery Mildew",
            "scientific_name": "Blumeria graminis f. sp. tritici",
            "symptoms": [
                "white powdery patches on leaves",
                "white fungal growth on stems",
                "curling of leaves",
                "stunted growth",
            ],
            "severity_factors": {"temperature_range": (15, 22), "humidity_min": 60},
            "favorable_months": [12, 1, 2],
            "growth_stages": ["vegetative", "flowering"],
            "treatment": {
                "chemical": "Sulfur 80% WP @ 2.5 g/L or Karathane 0.05% spray",
                "organic": "Baking soda solution (5 g/L); milk spray (1:9 dilution); improve air circulation",
                "preventive": "Avoid excess nitrogen; ensure proper spacing; grow resistant varieties",
            },
            "season": ["rabi"],
        },
        {
            "name": "Yellow Rust",
            "scientific_name": "Puccinia striiformis",
            "symptoms": [
                "yellow stripes on leaves",
                "linear rows of yellow pustules",
                "premature leaf drying",
                "reduced tillering",
            ],
            "severity_factors": {"temperature_range": (10, 18), "humidity_min": 80},
            "favorable_months": [12, 1, 2, 3],
            "growth_stages": ["seedling", "vegetative", "flowering"],
            "treatment": {
                "chemical": "Tilt (Propiconazole) 25 EC @ 0.1% or Bayleton (Triadimefon) 25 WP @ 0.1%",
                "organic": "Trichoderma-based bioagent spray; neem cake application in soil",
                "preventive": "Timely sowing; use resistant varieties (PBW-343, WH-1105); destroy volunteer plants",
            },
            "season": ["rabi"],
        },
        {
            "name": "Karnal Bunt",
            "scientific_name": "Tilletia indica",
            "symptoms": [
                "black powdery mass in grain",
                "fishy smell from grains",
                "partially converted kernels",
                "dark discoloration of seeds",
            ],
            "severity_factors": {"temperature_range": (18, 24), "humidity_min": 70},
            "favorable_months": [2, 3, 4],
            "growth_stages": ["flowering", "maturity"],
            "treatment": {
                "chemical": "Seed treatment with Thiram 75% WP @ 2.5 g/kg or Vitavax @ 2 g/kg seed",
                "organic": "Hot water seed treatment at 52°C for 10 min; Trichoderma viride seed treatment",
                "preventive": "Use certified disease-free seed; avoid irrigation during anthesis; early sowing",
            },
            "season": ["rabi"],
        },
    ],
    "rice": [
        {
            "name": "Blast",
            "scientific_name": "Magnaporthe oryzae",
            "symptoms": [
                "diamond shaped spots on leaves",
                "grey center lesions with brown margin",
                "neck rot at panicle base",
                "whitehead formation",
            ],
            "severity_factors": {"temperature_range": (24, 30), "humidity_min": 85},
            "favorable_months": [7, 8, 9, 10],
            "growth_stages": ["seedling", "vegetative", "flowering"],
            "treatment": {
                "chemical": "Tricyclazole 75% WP @ 0.6 g/L or Isoprothiolane 40 EC @ 1.5 mL/L",
                "organic": "Pseudomonas fluorescens spray @ 5 g/L; silicon amendment in soil",
                "preventive": "Avoid excess nitrogen; use resistant varieties (Tetep, CO-39); maintain proper water management",
            },
            "season": ["kharif"],
        },
        {
            "name": "Bacterial Leaf Blight",
            "scientific_name": "Xanthomonas oryzae pv. oryzae",
            "symptoms": [
                "water soaked lesions on leaf margins",
                "yellow to white lesions along veins",
                "wilting of seedlings",
                "milky ooze from cut lesions",
            ],
            "severity_factors": {"temperature_range": (25, 34), "humidity_min": 80},
            "favorable_months": [7, 8, 9],
            "growth_stages": ["vegetative", "flowering"],
            "treatment": {
                "chemical": "Streptomycin sulphate + Tetracycline (Plantomycin) @ 1 g/L; Copper oxychloride @ 2.5 g/L",
                "organic": "Neem oil 3% spray; proper drainage to reduce humidity",
                "preventive": "Avoid clipping of seedling tips during transplanting; balanced fertilization; field sanitation",
            },
            "season": ["kharif"],
        },
        {
            "name": "Sheath Blight",
            "scientific_name": "Rhizoctonia solani",
            "symptoms": [
                "oval or irregular greenish grey lesions on sheath",
                "banding pattern on leaf sheath",
                "lodging in severe cases",
                "sclerotia on infected tissue",
            ],
            "severity_factors": {"temperature_range": (28, 35), "humidity_min": 85},
            "favorable_months": [8, 9, 10],
            "growth_stages": ["vegetative", "flowering", "maturity"],
            "treatment": {
                "chemical": "Hexaconazole 5% EC @ 2 mL/L or Validamycin 3% SL @ 2.5 mL/L",
                "organic": "Trichoderma harzianum @ 5 g/L spray; avoid excess organic matter",
                "preventive": "Avoid dense planting; proper water management; remove sclerotia from field",
            },
            "season": ["kharif"],
        },
        {
            "name": "Brown Spot",
            "scientific_name": "Bipolaris oryzae",
            "symptoms": [
                "brown oval spots on leaves",
                "dark brown lesions on glumes",
                "seedling blight",
                "poor grain filling",
            ],
            "severity_factors": {"temperature_range": (25, 30), "humidity_min": 80},
            "favorable_months": [8, 9, 10, 11],
            "growth_stages": ["seedling", "vegetative", "flowering", "maturity"],
            "treatment": {
                "chemical": "Mancozeb 75% WP @ 2.5 g/L or Edifenphos 50 EC @ 1 mL/L",
                "organic": "Pseudomonas fluorescens seed treatment @ 10 g/kg seed; potash application",
                "preventive": "Balanced fertilization especially potash; seed treatment before sowing; proper field drainage",
            },
            "season": ["kharif"],
        },
    ],
    "cotton": [
        {
            "name": "Bacterial Blight",
            "scientific_name": "Xanthomonas citri subsp. malvacearum",
            "symptoms": [
                "angular water soaked spots on leaves",
                "black arm on stems",
                "boll rot",
                "vein blackening",
            ],
            "severity_factors": {"temperature_range": (25, 35), "humidity_min": 80},
            "favorable_months": [7, 8, 9, 10],
            "growth_stages": ["seedling", "vegetative", "flowering"],
            "treatment": {
                "chemical": "Streptocycline @ 1 g/10L + Copper oxychloride @ 2.5 g/L spray",
                "organic": "Neem seed kernel extract 5%; Pseudomonas fluorescens spray",
                "preventive": "Use acid-delinted certified seed; seed treatment with Carboxin; avoid overhead irrigation",
            },
            "season": ["kharif"],
        },
        {
            "name": "Fusarium Wilt",
            "scientific_name": "Fusarium oxysporum f. sp. vasinfectum",
            "symptoms": [
                "yellowing of leaves from bottom",
                "wilting of plants",
                "vascular browning in stem",
                "stunted growth",
            ],
            "severity_factors": {"temperature_range": (25, 33), "humidity_min": 60},
            "favorable_months": [6, 7, 8, 9],
            "growth_stages": ["vegetative", "flowering"],
            "treatment": {
                "chemical": "Carbendazim 50% WP @ 2 g/L soil drenching; Thiophanate-methyl seed treatment",
                "organic": "Trichoderma viride soil application @ 5 kg/ha; neem cake @ 150 kg/ha",
                "preventive": "Grow resistant varieties; crop rotation with non-host crops; proper drainage",
            },
            "season": ["kharif"],
        },
        {
            "name": "Grey Mildew",
            "scientific_name": "Ramularia areola",
            "symptoms": [
                "angular pale translucent spots on leaves",
                "white powdery growth on lower leaf surface",
                "premature defoliation",
                "reduced boll size",
            ],
            "severity_factors": {"temperature_range": (25, 30), "humidity_min": 70},
            "favorable_months": [9, 10, 11],
            "growth_stages": ["vegetative", "flowering", "maturity"],
            "treatment": {
                "chemical": "Carbendazim 50% WP @ 1 g/L or Mancozeb 75% WP @ 2.5 g/L foliar spray",
                "organic": "Sulfur dust application; improve air circulation by wider spacing",
                "preventive": "Remove and destroy infected plant debris; avoid excessive nitrogen; proper plant spacing",
            },
            "season": ["kharif"],
        },
    ],
    "maize": [
        {
            "name": "Northern Leaf Blight",
            "scientific_name": "Exserohilum turcicum",
            "symptoms": [
                "long elliptical grey-green lesions on leaves",
                "cigar shaped spots",
                "lesions turning tan to brown",
                "premature leaf senescence",
            ],
            "severity_factors": {"temperature_range": (18, 27), "humidity_min": 75},
            "favorable_months": [7, 8, 9],
            "growth_stages": ["vegetative", "flowering"],
            "treatment": {
                "chemical": "Mancozeb 75% WP @ 2.5 g/L or Zineb 75% WP @ 2 g/L at 10-day intervals",
                "organic": "Trichoderma viride foliar spray; neem oil 2% spray",
                "preventive": "Use resistant hybrids; crop rotation; destroy crop residues after harvest",
            },
            "season": ["kharif", "rabi"],
        },
        {
            "name": "Maydis Leaf Blight",
            "scientific_name": "Bipolaris maydis",
            "symptoms": [
                "small diamond shaped tan lesions",
                "elongated buff to brown spots",
                "lesions parallel to leaf veins",
                "extensive leaf blighting",
            ],
            "severity_factors": {"temperature_range": (20, 32), "humidity_min": 80},
            "favorable_months": [7, 8, 9, 10],
            "growth_stages": ["vegetative", "flowering", "maturity"],
            "treatment": {
                "chemical": "Zineb 75 WP @ 2 g/L or Dithane M-45 @ 2.5 g/L at weekly intervals",
                "organic": "Trichoderma-based foliar spray; improve field ventilation",
                "preventive": "Use tolerant varieties; avoid monocropping; remove infected debris",
            },
            "season": ["kharif"],
        },
        {
            "name": "Downy Mildew",
            "scientific_name": "Peronosclerospora sorghi",
            "symptoms": [
                "chlorotic streaks on leaves",
                "white downy growth on lower leaf surface",
                "stunted plants with excessive tillering",
                "leaf shredding into fine strips",
            ],
            "severity_factors": {"temperature_range": (20, 25), "humidity_min": 90},
            "favorable_months": [7, 8],
            "growth_stages": ["seedling", "vegetative"],
            "treatment": {
                "chemical": "Metalaxyl 35% WS seed treatment @ 3 g/kg seed; Ridomil MZ @ 2.5 g/L spray",
                "organic": "Remove and destroy infected plants immediately; improve drainage",
                "preventive": "Seed treatment with Metalaxyl; avoid late sowing; use resistant hybrids",
            },
            "season": ["kharif"],
        },
        {
            "name": "Stalk Rot",
            "scientific_name": "Fusarium verticillioides",
            "symptoms": [
                "rotting at the base of stalk",
                "shredded stalk pith",
                "premature drying of plants",
                "lodging of mature plants",
            ],
            "severity_factors": {"temperature_range": (26, 34), "humidity_min": 70},
            "favorable_months": [8, 9, 10],
            "growth_stages": ["flowering", "maturity"],
            "treatment": {
                "chemical": "Carbendazim 50% WP @ 2 g/L basal drench; avoid water stress during grain filling",
                "organic": "Trichoderma viride soil application; adequate potash fertilization",
                "preventive": "Balanced fertilization; avoid water logging; harvest at physiological maturity",
            },
            "season": ["kharif"],
        },
    ],
    "sugarcane": [
        {
            "name": "Red Rot",
            "scientific_name": "Colletotrichum falcatum",
            "symptoms": [
                "red discoloration of internal stalk tissue",
                "white patches interspersed with red areas",
                "withering and drying of crown leaves",
                "alcoholic smell from split cane",
            ],
            "severity_factors": {"temperature_range": (25, 32), "humidity_min": 80},
            "favorable_months": [7, 8, 9, 10],
            "growth_stages": ["vegetative", "maturity"],
            "treatment": {
                "chemical": "Sett treatment with Carbendazim 50% WP @ 2 g/L for 15 min before planting",
                "organic": "Trichoderma viride sett treatment; bioagent soil application",
                "preventive": "Use disease-free seed cane; grow resistant varieties (Co-0238); remove and destroy infected stools",
            },
            "season": ["kharif"],
        },
        {
            "name": "Smut",
            "scientific_name": "Sporisorium scitamineum",
            "symptoms": [
                "black whip-like structure from growing point",
                "thin tillers with grassy appearance",
                "excessive sprouting of side buds",
                "stunted cane growth",
            ],
            "severity_factors": {"temperature_range": (25, 35), "humidity_min": 60},
            "favorable_months": [4, 5, 6, 7],
            "growth_stages": ["vegetative", "flowering"],
            "treatment": {
                "chemical": "Sett treatment with Triadimefon 25% WP @ 2 g/L for 15 min",
                "organic": "Hot water treatment of setts at 52°C for 30 min; Trichoderma application",
                "preventive": "Use smut-free seed material; rogue out smutted clumps before whip opening; grow resistant varieties",
            },
            "season": ["kharif", "rabi"],
        },
        {
            "name": "Wilt",
            "scientific_name": "Fusarium sacchari",
            "symptoms": [
                "gradual yellowing and drying of leaves",
                "purplish red discoloration of internal tissue",
                "cavity formation in stalks",
                "pith turning brown and hollow",
            ],
            "severity_factors": {"temperature_range": (28, 36), "humidity_min": 70},
            "favorable_months": [6, 7, 8, 9, 10],
            "growth_stages": ["vegetative", "maturity"],
            "treatment": {
                "chemical": "Carbendazim 50% WP sett dip @ 2 g/L; soil drenching with Copper oxychloride",
                "organic": "Trichoderma viride soil application @ 5 kg/ha with FYM; organic amendments",
                "preventive": "Avoid waterlogging; use resistant varieties; remove infected stools; practice crop rotation",
            },
            "season": ["kharif"],
        },
    ],
}

# Season-to-month mapping
SEASON_MONTHS: dict[str, list[int]] = {
    "kharif": [6, 7, 8, 9, 10],
    "rabi": [10, 11, 12, 1, 2, 3],
    "zaid": [3, 4, 5, 6],
}

# Region-specific risk factors (higher multiplier = more risk)
REGION_RISK: dict[str, dict[str, float]] = {
    "punjab": {
        "wheat": 1.3,
        "rice": 1.2,
        "cotton": 1.1,
        "maize": 1.0,
        "sugarcane": 1.1,
    },
    "haryana": {
        "wheat": 1.2,
        "rice": 1.1,
        "cotton": 1.2,
        "maize": 1.0,
        "sugarcane": 1.0,
    },
    "uttar pradesh": {
        "wheat": 1.2,
        "rice": 1.1,
        "cotton": 0.8,
        "maize": 1.0,
        "sugarcane": 1.4,
    },
    "madhya pradesh": {
        "wheat": 1.3,
        "rice": 0.9,
        "cotton": 1.1,
        "maize": 1.1,
        "sugarcane": 0.9,
    },
    "maharashtra": {
        "wheat": 0.8,
        "rice": 0.9,
        "cotton": 1.4,
        "maize": 1.0,
        "sugarcane": 1.3,
    },
    "karnataka": {
        "wheat": 0.6,
        "rice": 1.1,
        "cotton": 1.0,
        "maize": 1.2,
        "sugarcane": 1.2,
    },
    "andhra pradesh": {
        "wheat": 0.5,
        "rice": 1.3,
        "cotton": 1.2,
        "maize": 1.0,
        "sugarcane": 1.0,
    },
    "tamil nadu": {
        "wheat": 0.3,
        "rice": 1.3,
        "cotton": 1.0,
        "maize": 1.1,
        "sugarcane": 1.2,
    },
    "west bengal": {
        "wheat": 0.7,
        "rice": 1.4,
        "cotton": 0.5,
        "maize": 0.9,
        "sugarcane": 0.8,
    },
    "gujarat": {
        "wheat": 1.0,
        "rice": 0.8,
        "cotton": 1.3,
        "maize": 1.0,
        "sugarcane": 1.1,
    },
    "rajasthan": {
        "wheat": 1.1,
        "rice": 0.5,
        "cotton": 1.0,
        "maize": 1.0,
        "sugarcane": 0.6,
    },
    "bihar": {"wheat": 1.1, "rice": 1.2, "cotton": 0.5, "maize": 1.3, "sugarcane": 1.0},
}

# ============================================================
# Pesticide Shop Database (simulated)
# ============================================================

PESTICIDE_SHOPS: list[dict] = [
    {
        "name": "Kisan Agro Centre",
        "address": "NH-44, Karnal, Haryana",
        "lat": 29.6857,
        "lon": 76.9905,
        "phone": "+91-184-2250100",
        "rating": 4.5,
        "products": {
            "Propiconazole 25% EC": 520,
            "Mancozeb 75% WP": 380,
            "Carbendazim 50% WP": 290,
            "Sulfur 80% WP": 210,
            "Neem Oil (1L)": 350,
            "Tricyclazole 75% WP": 680,
        },
    },
    {
        "name": "Bharat Krishi Seva Kendra",
        "address": "GT Road, Ludhiana, Punjab",
        "lat": 30.9010,
        "lon": 75.8573,
        "phone": "+91-161-2401234",
        "rating": 4.3,
        "products": {
            "Propiconazole 25% EC": 510,
            "Mancozeb 75% WP": 370,
            "Streptocycline": 180,
            "Copper Oxychloride": 310,
            "Hexaconazole 5% EC": 450,
            "Metalaxyl 35% WS": 620,
        },
    },
    {
        "name": "Shri Ganesh Pesticides",
        "address": "Mandi Road, Indore, Madhya Pradesh",
        "lat": 22.7196,
        "lon": 75.8577,
        "phone": "+91-731-2543210",
        "rating": 4.1,
        "products": {
            "Carbendazim 50% WP": 280,
            "Mancozeb 75% WP": 390,
            "Propiconazole 25% EC": 540,
            "Thiram 75% WP": 250,
            "Trichoderma viride (1kg)": 320,
            "Neem Oil (1L)": 340,
        },
    },
    {
        "name": "Jai Kisan Agro Store",
        "address": "Station Road, Nagpur, Maharashtra",
        "lat": 21.1458,
        "lon": 79.0882,
        "phone": "+91-712-2720456",
        "rating": 4.4,
        "products": {
            "Carbendazim 50% WP": 300,
            "Copper Oxychloride": 320,
            "Streptocycline": 175,
            "Mancozeb 75% WP": 395,
            "Propiconazole 25% EC": 530,
            "Thiophanate-methyl": 470,
        },
    },
    {
        "name": "Patel Agri Inputs",
        "address": "Ashram Road, Ahmedabad, Gujarat",
        "lat": 23.0225,
        "lon": 72.5714,
        "phone": "+91-79-26580012",
        "rating": 4.6,
        "products": {
            "Mancozeb 75% WP": 360,
            "Sulfur 80% WP": 200,
            "Tricyclazole 75% WP": 670,
            "Validamycin 3% SL": 540,
            "Zineb 75% WP": 310,
            "Neem Oil (1L)": 360,
        },
    },
    {
        "name": "Annapurna Seeds & Chemicals",
        "address": "Kanpur Road, Lucknow, Uttar Pradesh",
        "lat": 26.8467,
        "lon": 80.9462,
        "phone": "+91-522-2638900",
        "rating": 4.2,
        "products": {
            "Propiconazole 25% EC": 530,
            "Carbendazim 50% WP": 295,
            "Triadimefon 25% WP": 480,
            "Thiram 75% WP": 245,
            "Trichoderma viride (1kg)": 310,
            "Isoprothiolane 40 EC": 590,
        },
    },
    {
        "name": "Sri Lakshmi Agro",
        "address": "MG Road, Vijayawada, Andhra Pradesh",
        "lat": 16.5062,
        "lon": 80.6480,
        "phone": "+91-866-2578100",
        "rating": 4.0,
        "products": {
            "Tricyclazole 75% WP": 690,
            "Isoprothiolane 40 EC": 580,
            "Hexaconazole 5% EC": 440,
            "Pseudomonas fluorescens (1kg)": 400,
            "Edifenphos 50 EC": 520,
            "Copper Oxychloride": 305,
        },
    },
    {
        "name": "Karnataka Agri Mart",
        "address": "JC Road, Bengaluru, Karnataka",
        "lat": 12.9716,
        "lon": 77.5946,
        "phone": "+91-80-22870034",
        "rating": 4.7,
        "products": {
            "Mancozeb 75% WP": 375,
            "Carbendazim 50% WP": 285,
            "Metalaxyl 35% WS": 630,
            "Ridomil MZ": 710,
            "Neem Oil (1L)": 330,
            "Sulfur 80% WP": 195,
        },
    },
    {
        "name": "Tamil Nadu Pesticides Depot",
        "address": "Anna Salai, Chennai, Tamil Nadu",
        "lat": 13.0827,
        "lon": 80.2707,
        "phone": "+91-44-28520067",
        "rating": 4.3,
        "products": {
            "Tricyclazole 75% WP": 700,
            "Mancozeb 75% WP": 385,
            "Carbendazim 50% WP": 275,
            "Pseudomonas fluorescens (1kg)": 390,
            "Validamycin 3% SL": 550,
            "Copper Oxychloride": 315,
        },
    },
    {
        "name": "Rajasthan Krishi Udyog",
        "address": "Tonk Road, Jaipur, Rajasthan",
        "lat": 26.9124,
        "lon": 75.7873,
        "phone": "+91-141-2550890",
        "rating": 3.9,
        "products": {
            "Propiconazole 25% EC": 545,
            "Sulfur 80% WP": 215,
            "Mancozeb 75% WP": 400,
            "Zineb 75% WP": 320,
            "Neem Oil (1L)": 370,
            "Thiram 75% WP": 260,
        },
    },
    {
        "name": "Bengal Agro Services",
        "address": "Jessore Road, Kolkata, West Bengal",
        "lat": 22.5726,
        "lon": 88.3639,
        "phone": "+91-33-25560078",
        "rating": 4.1,
        "products": {
            "Tricyclazole 75% WP": 685,
            "Isoprothiolane 40 EC": 575,
            "Mancozeb 75% WP": 365,
            "Edifenphos 50 EC": 515,
            "Hexaconazole 5% EC": 455,
            "Neem Oil (1L)": 345,
        },
    },
    {
        "name": "Punjab Agri Solutions",
        "address": "Mall Road, Amritsar, Punjab",
        "lat": 31.6340,
        "lon": 74.8723,
        "phone": "+91-183-2563200",
        "rating": 4.4,
        "products": {
            "Propiconazole 25% EC": 505,
            "Triadimefon 25% WP": 475,
            "Carbendazim 50% WP": 270,
            "Streptocycline": 170,
            "Trichoderma viride (1kg)": 305,
            "Sulfur 80% WP": 205,
        },
    },
    {
        "name": "Deccan Agri Hub",
        "address": "Tilak Road, Pune, Maharashtra",
        "lat": 18.5204,
        "lon": 73.8567,
        "phone": "+91-20-24450189",
        "rating": 4.5,
        "products": {
            "Carbendazim 50% WP": 310,
            "Mancozeb 75% WP": 385,
            "Copper Oxychloride": 330,
            "Thiophanate-methyl": 465,
            "Neem Oil (1L)": 355,
            "Trichoderma viride (1kg)": 330,
        },
    },
    {
        "name": "Madhya Bharat Kisan Store",
        "address": "AB Road, Bhopal, Madhya Pradesh",
        "lat": 23.2599,
        "lon": 77.4126,
        "phone": "+91-755-2770345",
        "rating": 4.0,
        "products": {
            "Propiconazole 25% EC": 525,
            "Thiram 75% WP": 240,
            "Metalaxyl 35% WS": 615,
            "Zineb 75% WP": 305,
            "Carbendazim 50% WP": 285,
            "Validamycin 3% SL": 535,
        },
    },
    {
        "name": "Telangana Seeds & Pesticides",
        "address": "Begumpet, Hyderabad, Telangana",
        "lat": 17.3850,
        "lon": 78.4867,
        "phone": "+91-40-27760023",
        "rating": 4.2,
        "products": {
            "Tricyclazole 75% WP": 695,
            "Hexaconazole 5% EC": 445,
            "Isoprothiolane 40 EC": 585,
            "Mancozeb 75% WP": 370,
            "Pseudomonas fluorescens (1kg)": 410,
            "Edifenphos 50 EC": 525,
        },
    },
    {
        "name": "Bihar Kisan Seva",
        "address": "Bailey Road, Patna, Bihar",
        "lat": 25.6093,
        "lon": 85.1376,
        "phone": "+91-612-2230056",
        "rating": 3.8,
        "products": {
            "Mancozeb 75% WP": 395,
            "Carbendazim 50% WP": 300,
            "Tricyclazole 75% WP": 710,
            "Neem Oil (1L)": 335,
            "Propiconazole 25% EC": 550,
            "Trichoderma viride (1kg)": 315,
        },
    },
]

# Mapping from disease treatment keywords to product names in the shop database
DISEASE_PRODUCT_MAP: dict[str, list[str]] = {
    "Leaf Rust": ["Propiconazole 25% EC", "Neem Oil (1L)"],
    "Powdery Mildew": ["Sulfur 80% WP", "Neem Oil (1L)"],
    "Yellow Rust": [
        "Propiconazole 25% EC",
        "Triadimefon 25% WP",
        "Trichoderma viride (1kg)",
    ],
    "Karnal Bunt": ["Thiram 75% WP", "Trichoderma viride (1kg)"],
    "Blast": [
        "Tricyclazole 75% WP",
        "Isoprothiolane 40 EC",
        "Pseudomonas fluorescens (1kg)",
    ],
    "Bacterial Leaf Blight": ["Streptocycline", "Copper Oxychloride", "Neem Oil (1L)"],
    "Sheath Blight": [
        "Hexaconazole 5% EC",
        "Validamycin 3% SL",
        "Trichoderma viride (1kg)",
    ],
    "Brown Spot": [
        "Mancozeb 75% WP",
        "Edifenphos 50 EC",
        "Pseudomonas fluorescens (1kg)",
    ],
    "Bacterial Blight": [
        "Streptocycline",
        "Copper Oxychloride",
        "Pseudomonas fluorescens (1kg)",
    ],
    "Fusarium Wilt": [
        "Carbendazim 50% WP",
        "Thiophanate-methyl",
        "Trichoderma viride (1kg)",
    ],
    "Grey Mildew": ["Carbendazim 50% WP", "Mancozeb 75% WP", "Sulfur 80% WP"],
    "Northern Leaf Blight": [
        "Mancozeb 75% WP",
        "Zineb 75% WP",
        "Trichoderma viride (1kg)",
    ],
    "Maydis Leaf Blight": ["Zineb 75% WP", "Mancozeb 75% WP"],
    "Downy Mildew": ["Metalaxyl 35% WS", "Ridomil MZ"],
    "Stalk Rot": ["Carbendazim 50% WP", "Trichoderma viride (1kg)"],
    "Red Rot": ["Carbendazim 50% WP", "Trichoderma viride (1kg)"],
    "Smut": ["Triadimefon 25% WP", "Trichoderma viride (1kg)"],
    "Wilt": ["Carbendazim 50% WP", "Copper Oxychloride", "Trichoderma viride (1kg)"],
}

# ============================================================
# Disease-to-Protein Engineering Map (simulated research data)
# ============================================================

DISEASE_PROTEIN_MAP: dict[str, dict] = {
    "Leaf Rust": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "Lr34",
                "protein": "ABC transporter protein",
                "function": "Multi-pathogen resistance including leaf rust, stripe rust, and powdery mildew",
            },
            {
                "gene": "Lr21",
                "protein": "NBS-LRR resistance protein",
                "function": "Race-specific resistance to Puccinia triticina",
            },
        ],
        "research_status": "Advanced — Lr34 is well-characterized and deployed in multiple wheat varieties worldwide",
        "engineering_approach": "CRISPR-Cas9 editing of susceptibility genes; overexpression of Lr34 orthologs",
    },
    "Powdery Mildew": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "Pm3",
                "protein": "NBS-LRR immune receptor",
                "function": "Recognition of powdery mildew effector proteins",
            },
            {
                "gene": "MLO",
                "protein": "MLO transmembrane protein (loss-of-function)",
                "function": "Broad-spectrum resistance when knocked out",
            },
        ],
        "research_status": "Advanced — mlo-based resistance successfully deployed in barley and being adapted for wheat",
        "engineering_approach": "Targeted knockout of MLO homologs via CRISPR; stacking Pm3 alleles for broad resistance",
    },
    "Yellow Rust": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "Yr15",
                "protein": "Tandem kinase-pseudokinase protein (WTK1)",
                "function": "Broad-spectrum resistance to stripe rust races",
            },
            {
                "gene": "Yr36",
                "protein": "Wheat kinase START protein (WKS1)",
                "function": "Temperature-dependent stripe rust resistance",
            },
        ],
        "research_status": "Active research — Yr15 recently cloned and showing broad resistance spectrum",
        "engineering_approach": "Introgression of Yr15 via marker-assisted selection; protein engineering of WKS1 for temperature-stable resistance",
    },
    "Karnal Bunt": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "TaWRKY76",
                "protein": "WRKY transcription factor",
                "function": "Regulation of defense pathways against Tilletia indica",
            },
            {
                "gene": "TaPR1",
                "protein": "Pathogenesis-related protein 1",
                "function": "Antifungal activity in wheat spikes",
            },
        ],
        "research_status": "Early research — QTLs identified but no single major resistance gene cloned yet",
        "engineering_approach": "Overexpression of defense-related transcription factors; engineering enhanced PR protein variants",
    },
    "Blast": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "Pi-ta",
                "protein": "NBS-LRR cytoplasmic receptor",
                "function": "Direct recognition of Magnaporthe oryzae AVR-Pita effector",
            },
            {
                "gene": "Pi9",
                "protein": "NBS-LRR resistance protein",
                "function": "Broad-spectrum blast resistance",
            },
            {
                "gene": "Pigm",
                "protein": "Paired NLR immune receptors (PigmR/PigmS)",
                "function": "Balanced broad-spectrum resistance without yield penalty",
            },
        ],
        "research_status": "Advanced — Pi-ta and Pigm are well-characterized; Pigm deployed in Chinese rice varieties",
        "engineering_approach": "Pyramiding Pi-ta, Pi9, and Pigm via molecular breeding; engineering enhanced NLR receptor variants",
    },
    "Bacterial Leaf Blight": {
        "pathogen_type": "Bacterium",
        "target_proteins": [
            {
                "gene": "Xa21",
                "protein": "Receptor-like kinase (RLK)",
                "function": "Pattern recognition receptor for Xanthomonas oryzae",
            },
            {
                "gene": "Xa13 (loss-of-function)",
                "protein": "SWEET sugar transporter",
                "function": "Resistance by blocking pathogen sugar access when mutated",
            },
        ],
        "research_status": "Advanced — Xa21 is a landmark gene in plant immunity; SWEET engineering is cutting-edge",
        "engineering_approach": "CRISPR-based editing of SWEET gene promoters to prevent TAL effector binding; Xa21 transfer to susceptible varieties",
    },
    "Sheath Blight": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "OsWRKY30",
                "protein": "WRKY transcription factor",
                "function": "Positive regulator of defense against Rhizoctonia solani",
            },
            {
                "gene": "OsCHI11",
                "protein": "Chitinase class I",
                "function": "Degradation of fungal cell wall chitin",
            },
        ],
        "research_status": "Moderate — no major R-gene identified; transgenic approaches showing promise",
        "engineering_approach": "Overexpression of chitinase genes; engineering synthetic antimicrobial peptides targeting Rhizoctonia",
    },
    "Brown Spot": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "OsNPR1",
                "protein": "NPR1 regulatory protein",
                "function": "Master regulator of systemic acquired resistance (SAR)",
            },
            {
                "gene": "OsPR10",
                "protein": "Pathogenesis-related protein 10",
                "function": "Ribonuclease activity against fungal pathogens",
            },
        ],
        "research_status": "Moderate — NPR1 overexpression shows enhanced resistance in transgenic lines",
        "engineering_approach": "Engineering enhanced NPR1 variants for stronger SAR activation; combining with silicon uptake genes",
    },
    "Bacterial Blight": {
        "pathogen_type": "Bacterium",
        "target_proteins": [
            {
                "gene": "GhMPK3",
                "protein": "Mitogen-activated protein kinase 3",
                "function": "Signal transduction in cotton defense against Xanthomonas",
            },
            {
                "gene": "GhWRKY25",
                "protein": "WRKY transcription factor",
                "function": "Positive regulator of immune response in cotton",
            },
        ],
        "research_status": "Early-moderate — defense signaling pathways being mapped in cotton",
        "engineering_approach": "Overexpression of defense kinase cascades; engineering enhanced pathogen recognition receptors",
    },
    "Fusarium Wilt": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "Fov1 (candidate)",
                "protein": "NBS-LRR resistance protein",
                "function": "Candidate resistance gene for Fusarium oxysporum f. sp. vasinfectum",
            },
            {
                "gene": "GhERF1",
                "protein": "Ethylene response factor 1",
                "function": "Activation of defense genes in root vascular tissue",
            },
        ],
        "research_status": "Active research — resistance QTLs mapped; gene stacking approaches being tested",
        "engineering_approach": "Enhancing root defense through ERF transcription factor engineering; CRISPR-based susceptibility gene knockouts",
    },
    "Grey Mildew": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "GhPR5",
                "protein": "Thaumatin-like protein",
                "function": "Antifungal activity against Ramularia areola",
            },
            {
                "gene": "GhNPR1",
                "protein": "NPR1 transcriptional co-activator",
                "function": "Broad-spectrum defense activation in cotton",
            },
        ],
        "research_status": "Early — limited molecular studies; focus on conventional breeding for resistance",
        "engineering_approach": "Transfer of enhanced NPR1 variants; engineering thaumatin-like proteins with improved antifungal spectrum",
    },
    "Northern Leaf Blight": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "Ht1",
                "protein": "NBS-LRR chloroplast-targeted protein",
                "function": "Race-specific resistance to Exserohilum turcicum",
            },
            {
                "gene": "ZmRXO1",
                "protein": "NBS-LRR resistance protein",
                "function": "Non-host resistance providing broad protection",
            },
        ],
        "research_status": "Advanced — Ht1, Ht2, Ht3 genes well-characterized; gene pyramiding in progress",
        "engineering_approach": "Stacking multiple Ht resistance genes; engineering enhanced NLR receptors for broader race recognition",
    },
    "Maydis Leaf Blight": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "ZmLOX3 (loss-of-function)",
                "protein": "Lipoxygenase 3",
                "function": "Susceptibility factor — knockout enhances resistance",
            },
            {
                "gene": "ZmPR4",
                "protein": "Pathogenesis-related protein 4 (chitinase)",
                "function": "Antifungal defense against Bipolaris maydis",
            },
        ],
        "research_status": "Moderate — T-cytoplasm vulnerability (historical) now avoided; polygenic resistance being enhanced",
        "engineering_approach": "CRISPR knockout of ZmLOX3; overexpression of antifungal PR proteins",
    },
    "Downy Mildew": {
        "pathogen_type": "Oomycete",
        "target_proteins": [
            {
                "gene": "ZmRpp9",
                "protein": "NBS-LRR resistance protein",
                "function": "Major gene resistance against Peronosclerospora sorghi",
            },
            {
                "gene": "ZmPAL",
                "protein": "Phenylalanine ammonia-lyase",
                "function": "Key enzyme in phenylpropanoid defense pathway",
            },
        ],
        "research_status": "Moderate — Rpp9 provides strong resistance; additional QTLs being mapped",
        "engineering_approach": "Marker-assisted pyramiding of Rpp9 with minor QTLs; enhancing phenylpropanoid pathway flux",
    },
    "Stalk Rot": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "ZmCCT (qRfg1)",
                "protein": "CCT domain transcription factor",
                "function": "Major QTL for Gibberella stalk rot resistance in maize",
            },
            {
                "gene": "ZmAuxRP1",
                "protein": "Auxin-regulated protein",
                "function": "Defense activation in stalk tissues",
            },
        ],
        "research_status": "Active research — qRfg1 cloned and validated; auxin signaling role being explored",
        "engineering_approach": "Introgression of qRfg1 via marker-assisted selection; engineering stalk-specific defense activation",
    },
    "Red Rot": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "ScCHI",
                "protein": "Chitinase",
                "function": "Cell wall degrading enzyme targeting Colletotrichum falcatum",
            },
            {
                "gene": "ScNBS-LRR (candidate)",
                "protein": "NBS-LRR resistance gene family",
                "function": "Pathogen recognition in sugarcane",
            },
        ],
        "research_status": "Early-moderate — sugarcane's complex polyploid genome complicates gene identification",
        "engineering_approach": "Transgenic overexpression of chitinase and glucanase genes; RNAi-based silencing of pathogen virulence factors",
    },
    "Smut": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "ScR1MYB1",
                "protein": "MYB transcription factor",
                "function": "Regulation of phenylpropanoid defense pathway in sugarcane",
            },
            {
                "gene": "ScGLP",
                "protein": "Germin-like protein",
                "function": "Oxalate oxidase activity generating H2O2 for defense",
            },
        ],
        "research_status": "Early — molecular basis of smut resistance poorly understood due to genome complexity",
        "engineering_approach": "Engineering enhanced oxidative burst response; overexpression of defense-related transcription factors",
    },
    "Wilt": {
        "pathogen_type": "Fungus",
        "target_proteins": [
            {
                "gene": "ScERF1",
                "protein": "Ethylene response factor",
                "function": "Activation of defense genes in sugarcane vascular tissue",
            },
            {
                "gene": "ScPR1",
                "protein": "Pathogenesis-related protein 1",
                "function": "Systemic acquired resistance marker in sugarcane",
            },
        ],
        "research_status": "Early — limited functional genomics data for Fusarium sacchari resistance",
        "engineering_approach": "Engineering vascular-specific defense expression; CRISPR-based approaches pending improved sugarcane transformation",
    },
}

# DB: detection_history → DiseaseDetection table

# ============================================================
# Pydantic Models
# ============================================================


class DiseaseDetectionRequest(BaseModel):
    crop: str = Field(
        ..., description="Crop name (e.g. wheat, rice, cotton, maize, sugarcane)"
    )
    symptoms: list[str] = Field(
        ..., min_length=1, description="List of observed symptoms"
    )
    temperature_celsius: Optional[float] = Field(
        None, description="Current temperature in Celsius"
    )
    humidity_pct: Optional[float] = Field(
        None, ge=0, le=100, description="Current relative humidity %"
    )
    region: Optional[str] = Field(None, description="Region/state name")
    growth_stage: Optional[str] = Field(
        None, description="Growth stage: seedling, vegetative, flowering, or maturity"
    )


class TreatmentResponse(BaseModel):
    chemical: str
    organic: str
    preventive: str


class DiseaseMatch(BaseModel):
    name: str
    scientific_name: str
    confidence: float = Field(..., ge=0, le=1, description="Confidence score 0-1")
    matched_symptoms: list[str]
    severity_assessment: str
    treatment: TreatmentResponse


class DetectionResponse(BaseModel):
    detection_id: str
    status: str
    crop: str
    disease_detected: bool
    top_matches: list[DiseaseMatch]
    environmental_note: Optional[str] = None
    detected_at: str


class RecommendationDisease(BaseModel):
    name: str
    scientific_name: str
    risk_level: str
    peak_months: list[str]
    key_symptoms: list[str]
    treatment: TreatmentResponse


class RecommendationResponse(BaseModel):
    crop: str
    season: str
    region: Optional[str]
    diseases: list[RecommendationDisease]
    general_preventive_measures: list[str]


class AlertItem(BaseModel):
    alert_id: str
    severity: str
    crop: str
    disease_name: str
    risk_score: float
    advisory: str
    issued_at: str


class AlertsResponse(BaseModel):
    region: str
    season: str
    current_month: str
    alerts: list[AlertItem]


class HistoryEntry(BaseModel):
    detection_id: str
    crop: str
    top_disease: Optional[str]
    confidence: Optional[float]
    detected_at: str


class HistoryResponse(BaseModel):
    count: int
    detections: list[HistoryEntry]


class NearbyShopsRequest(BaseModel):
    latitude: float = Field(
        ..., ge=-90, le=90, description="Latitude of the user's location"
    )
    longitude: float = Field(
        ..., ge=-180, le=180, description="Longitude of the user's location"
    )
    disease_name: Optional[str] = Field(
        None, description="Disease name to filter relevant pesticides"
    )
    crop: str = Field(
        ..., description="Crop name (e.g. wheat, rice, cotton, maize, sugarcane)"
    )


class PesticideProduct(BaseModel):
    name: str
    price_inr: float
    availability: bool = True


class ShopResult(BaseModel):
    name: str
    address: str
    distance_km: float
    phone: str
    rating: float
    relevant_products: list[PesticideProduct]


class NearbyShopsResponse(BaseModel):
    query_location: dict
    crop: str
    disease_filter: Optional[str]
    shops_found: int
    shops: list[ShopResult]


class ProteinEngineeringRequest(BaseModel):
    disease_name: str = Field(..., description="Name of the crop disease")
    crop: str = Field(..., description="Crop name")
    pathogen_info: Optional[str] = Field(
        None, description="Additional pathogen information"
    )


class TargetProtein(BaseModel):
    gene: str
    protein: str
    function: str


class ProteinEngineeringResponse(BaseModel):
    disease_name: str
    crop: str
    pathogen: str
    pathogen_type: str
    target_proteins: list[TargetProtein]
    research_status: str
    engineering_approach: str
    protein_engineering_service_link: str
    message: str


# ============================================================
# Helper functions
# ============================================================

MONTH_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _current_month() -> int:
    return datetime.now(timezone.utc).month


def _current_season() -> str:
    month = _current_month()
    if month in SEASON_MONTHS["kharif"]:
        return "kharif"
    if month in SEASON_MONTHS["rabi"]:
        return "rabi"
    return "zaid"


def _symptom_score(
    disease_symptoms: list[str], reported_symptoms: list[str]
) -> tuple[float, list[str]]:
    """Score how well reported symptoms match a disease.

    Uses keyword overlap: each reported symptom is checked against each disease
    symptom for common significant words (length > 3 to skip articles/prepositions).
    Returns (score 0-1, list of matched disease symptoms).
    """
    matched: list[str] = []
    for ds in disease_symptoms:
        ds_words = {w.lower() for w in ds.split() if len(w) > 3}
        for rs in reported_symptoms:
            rs_words = {w.lower() for w in rs.split() if len(w) > 3}
            overlap = ds_words & rs_words
            if overlap:
                matched.append(ds)
                break
    if not disease_symptoms:
        return 0.0, matched
    return len(matched) / len(disease_symptoms), matched


def _environmental_factor(
    disease: dict,
    temperature: Optional[float],
    humidity: Optional[float],
) -> float:
    """Return a multiplier (0.5 - 1.5) based on how favourable the environment is."""
    factor = 1.0
    sf = disease.get("severity_factors", {})
    temp_range = sf.get("temperature_range")
    hum_min = sf.get("humidity_min")

    if temperature is not None and temp_range:
        lo, hi = temp_range
        if lo <= temperature <= hi:
            factor += 0.25  # ideal range
        elif abs(temperature - lo) <= 5 or abs(temperature - hi) <= 5:
            factor += 0.0  # near range, neutral
        else:
            factor -= 0.25  # far from ideal

    if humidity is not None and hum_min is not None:
        if humidity >= hum_min:
            factor += 0.20
        elif humidity >= hum_min - 15:
            factor += 0.0
        else:
            factor -= 0.20

    return max(0.1, min(factor, 1.5))


def _growth_stage_factor(disease: dict, stage: Optional[str]) -> float:
    """Return multiplier based on growth stage relevance."""
    if stage is None:
        return 1.0
    stages = disease.get("growth_stages", [])
    if not stages:
        return 1.0
    if stage.lower() in [s.lower() for s in stages]:
        return 1.15
    return 0.85


def _severity_label(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.45:
        return "moderate"
    if confidence >= 0.20:
        return "low"
    return "minimal"


def _month_factor(disease: dict) -> float:
    """Boost if current month is in the disease's favourable months."""
    favourable = disease.get("favorable_months", [])
    if not favourable:
        return 1.0
    if _current_month() in favourable:
        return 1.15
    return 0.90


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Haversine distance in kilometres between two lat/lon points."""
    r = 6371.0  # Earth radius in km
    lat1_r, lon1_r, lat2_r, lon2_r = np.radians([lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return float(round(r * c, 2))


def _find_disease_in_kb(
    disease_name: str, crop: Optional[str] = None
) -> Optional[dict]:
    """Look up a disease by name in the CROP_DISEASES knowledge base."""
    search_name = disease_name.strip().lower()
    crops_to_search = (
        {crop.strip().lower(): CROP_DISEASES[crop.strip().lower()]}
        if crop and crop.strip().lower() in CROP_DISEASES
        else CROP_DISEASES
    )
    for _crop_key, diseases in crops_to_search.items():
        for d in diseases:
            if d["name"].lower() == search_name:
                return d
    return None


# ============================================================
# Lifespan
# ============================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup resources."""
    await init_db()
    yield
    await close_db()


# ============================================================
# App setup
# ============================================================

app = FastAPI(
    title="Fasal Rakshak",
    description="Crop disease detection and pest management recommendations",
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
        "service": "fasal_rakshak",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint returning service info."""
    return {
        "service": "Fasal Rakshak",
        "version": "1.0.0",
        "features": [
            "Symptom-based crop disease detection",
            "Environmental condition analysis",
            "Treatment and pesticide recommendations",
            "Region-specific pest alerts",
        ],
    }


@app.post("/detect", response_model=DetectionResponse)
async def detect_disease(
    req: DiseaseDetectionRequest, db: AsyncSession = Depends(get_db)
):
    """Detect crop disease from reported symptoms and environmental data."""
    crop_key = req.crop.strip().lower()
    diseases = CROP_DISEASES.get(crop_key)
    if diseases is None:
        supported = ", ".join(sorted(CROP_DISEASES.keys()))
        raise HTTPException(
            status_code=400,
            detail=f"Crop '{req.crop}' not found in knowledge base. Supported crops: {supported}",
        )

    scored: list[tuple[float, dict, list[str]]] = []
    for disease in diseases:
        sym_score, matched_syms = _symptom_score(disease["symptoms"], req.symptoms)
        env_factor = _environmental_factor(
            disease, req.temperature_celsius, req.humidity_pct
        )
        stage_factor = _growth_stage_factor(disease, req.growth_stage)
        month_factor = _month_factor(disease)

        raw_confidence = sym_score * env_factor * stage_factor * month_factor

        # Apply region factor
        if req.region:
            region_key = req.region.strip().lower()
            region_factors = REGION_RISK.get(region_key, {})
            region_mult = region_factors.get(crop_key, 1.0)
            raw_confidence *= region_mult

        # Clamp to [0, 1]
        confidence = max(0.0, min(round(raw_confidence, 4), 1.0))
        scored.append((confidence, disease, matched_syms))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:3]

    # Build environmental note
    env_notes: list[str] = []
    if req.temperature_celsius is not None:
        env_notes.append(f"Temperature {req.temperature_celsius}°C")
    if req.humidity_pct is not None:
        env_notes.append(f"Humidity {req.humidity_pct}%")
    if req.growth_stage:
        env_notes.append(f"Growth stage: {req.growth_stage}")
    env_note = "; ".join(env_notes) if env_notes else None

    disease_detected = len(top) > 0 and top[0][0] > 0.0

    matches = [
        DiseaseMatch(
            name=d["name"],
            scientific_name=d["scientific_name"],
            confidence=conf,
            matched_symptoms=msyms,
            severity_assessment=_severity_label(conf),
            treatment=TreatmentResponse(**d["treatment"]),
        )
        for conf, d, msyms in top
    ]

    detection_id = f"det-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    detected_at = datetime.now(timezone.utc).isoformat()

    # Store in history (DB)
    db.add(
        DiseaseDetection(
            detection_id=detection_id,
            crop=crop_key,
            top_disease=matches[0].name
            if matches and matches[0].confidence > 0
            else None,
            confidence=matches[0].confidence if matches else None,
            detected_at=detected_at,
        )
    )
    await db.flush()

    return DetectionResponse(
        detection_id=detection_id,
        status="completed",
        crop=crop_key,
        disease_detected=disease_detected,
        top_matches=matches,
        environmental_note=env_note,
        detected_at=detected_at,
    )


@app.get("/recommendations/{crop}", response_model=RecommendationResponse)
async def get_recommendations(
    crop: str,
    season: str = Query("kharif", description="Season: kharif, rabi, or zaid"),
    region: Optional[str] = Query(None, description="Region/state name"),
):
    """Get pest management recommendations for a specific crop and season."""
    crop_key = crop.strip().lower()
    diseases = CROP_DISEASES.get(crop_key)
    if diseases is None:
        supported = ", ".join(sorted(CROP_DISEASES.keys()))
        raise HTTPException(
            status_code=400,
            detail=f"Crop '{crop}' not found in knowledge base. Supported crops: {supported}",
        )

    season_key = season.strip().lower()
    if season_key not in SEASON_MONTHS:
        raise HTTPException(
            status_code=400, detail="Season must be one of: kharif, rabi, zaid"
        )

    season_months = SEASON_MONTHS[season_key]

    # Filter diseases relevant to the season
    relevant = []
    for d in diseases:
        d_seasons = d.get("season", [])
        if season_key in d_seasons or not d_seasons:
            relevant.append(d)

    # Score and sort by risk
    rec_diseases: list[RecommendationDisease] = []
    for d in relevant:
        favourable = d.get("favorable_months", [])
        overlap_months = [m for m in favourable if m in season_months]
        if overlap_months:
            risk = "high" if len(overlap_months) >= 3 else "medium"
        else:
            risk = "low"

        # Boost risk if region is a major grower
        if region:
            region_key = region.strip().lower()
            rm = REGION_RISK.get(region_key, {}).get(crop_key, 1.0)
            if rm >= 1.3 and risk == "medium":
                risk = "high"

        rec_diseases.append(
            RecommendationDisease(
                name=d["name"],
                scientific_name=d["scientific_name"],
                risk_level=risk,
                peak_months=[
                    MONTH_NAMES[m]
                    for m in d.get("favorable_months", [])
                    if 1 <= m <= 12
                ],
                key_symptoms=d["symptoms"][:3],
                treatment=TreatmentResponse(**d["treatment"]),
            )
        )

    # Sort: high > medium > low
    risk_order = {"high": 0, "medium": 1, "low": 2}
    rec_diseases.sort(key=lambda x: risk_order.get(x.risk_level, 3))

    general_measures = [
        f"Use certified disease-free seeds for {crop_key}",
        "Practice crop rotation with non-host crops (2-3 year cycle)",
        "Maintain balanced fertilization — avoid excess nitrogen",
        "Ensure proper field drainage to reduce humidity buildup",
        "Scout fields regularly (weekly) and report early symptoms",
        "Remove and destroy crop residues after harvest",
    ]

    return RecommendationResponse(
        crop=crop_key,
        season=season_key,
        region=region.strip().lower() if region else None,
        diseases=rec_diseases,
        general_preventive_measures=general_measures,
    )


@app.get("/alerts", response_model=AlertsResponse)
async def get_pest_alerts(
    region: str = Query(..., description="Region/state name (required)"),
    crop: Optional[str] = Query(None, description="Filter alerts by crop"),
):
    """Get active pest and disease alerts for a region based on current conditions."""
    region_key = region.strip().lower()
    month = _current_month()
    season = _current_season()

    # Determine which crops to scan
    if crop:
        crop_key = crop.strip().lower()
        if crop_key not in CROP_DISEASES:
            supported = ", ".join(sorted(CROP_DISEASES.keys()))
            raise HTTPException(
                status_code=400,
                detail=f"Crop '{crop}' not found. Supported: {supported}",
            )
        crops_to_check = {crop_key: CROP_DISEASES[crop_key]}
    else:
        crops_to_check = CROP_DISEASES

    alerts: list[AlertItem] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for c_name, diseases in crops_to_check.items():
        for d in diseases:
            # Check if disease is relevant this month
            favourable = d.get("favorable_months", [])
            if month not in favourable:
                continue

            # Base risk from month relevance
            risk = 0.5

            # Boost by region factor
            region_factors = REGION_RISK.get(region_key, {})
            region_mult = region_factors.get(c_name, 1.0)
            risk *= region_mult

            # Boost if current season matches disease season
            d_seasons = d.get("season", [])
            if season in d_seasons:
                risk *= 1.2

            risk = round(min(risk, 1.0), 2)

            if risk < 0.25:
                continue

            severity = (
                "critical" if risk >= 0.70 else "high" if risk >= 0.50 else "moderate"
            )

            treatment = d["treatment"]
            advisory = f"{severity.capitalize()} risk of {d['name']} in {c_name}. "
            advisory += f"Preventive: {treatment['preventive'][:120]}"

            alerts.append(
                AlertItem(
                    alert_id=f"alert-{c_name[:3]}-{d['name'][:3].lower()}-{uuid.uuid4().hex[:4]}",
                    severity=severity,
                    crop=c_name,
                    disease_name=d["name"],
                    risk_score=risk,
                    advisory=advisory,
                    issued_at=now_iso,
                )
            )

    # Sort by risk score descending
    alerts.sort(key=lambda a: a.risk_score, reverse=True)

    return AlertsResponse(
        region=region_key,
        season=season,
        current_month=MONTH_NAMES[month],
        alerts=alerts,
    )


@app.get("/history", response_model=HistoryResponse)
async def get_detection_history(
    crop: Optional[str] = Query(None, description="Filter by crop name"),
    db: AsyncSession = Depends(get_db),
):
    """Return detection history from database, optionally filtered by crop."""
    stmt = select(DiseaseDetection).order_by(DiseaseDetection.id.desc())
    if crop:
        crop_key = crop.strip().lower()
        stmt = stmt.where(DiseaseDetection.crop == crop_key)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    detections = [
        HistoryEntry(
            detection_id=r.detection_id,
            crop=r.crop,
            top_disease=r.top_disease,
            confidence=r.confidence,
            detected_at=r.detected_at,
        )
        for r in rows
    ]

    return HistoryResponse(count=len(detections), detections=detections)


@app.post("/nearby-shops", response_model=NearbyShopsResponse)
async def find_nearby_shops(req: NearbyShopsRequest):
    """Find nearby pesticide shops with prices relevant to a crop disease."""
    crop_key = req.crop.strip().lower()
    if crop_key not in CROP_DISEASES:
        supported = ", ".join(sorted(CROP_DISEASES.keys()))
        raise HTTPException(
            status_code=400,
            detail=f"Crop '{req.crop}' not found in knowledge base. Supported crops: {supported}",
        )

    # Determine which products are relevant for the disease
    relevant_product_names: list[str] | None = None
    disease_filter_name: str | None = None
    if req.disease_name:
        disease_filter_name = req.disease_name.strip()
        # Try exact match first, then case-insensitive
        relevant_product_names = DISEASE_PRODUCT_MAP.get(disease_filter_name)
        if relevant_product_names is None:
            for key, val in DISEASE_PRODUCT_MAP.items():
                if key.lower() == disease_filter_name.lower():
                    relevant_product_names = val
                    disease_filter_name = key
                    break
        # Validate the disease exists for this crop
        disease_record = _find_disease_in_kb(disease_filter_name, crop_key)
        if disease_record is None:
            raise HTTPException(
                status_code=404,
                detail=f"Disease '{req.disease_name}' not found for crop '{crop_key}' in knowledge base.",
            )

    # Calculate distance from user to each shop and sort
    shop_distances: list[tuple[float, dict]] = []
    for shop in PESTICIDE_SHOPS:
        dist = _haversine_km(req.latitude, req.longitude, shop["lat"], shop["lon"])
        shop_distances.append((dist, shop))

    shop_distances.sort(key=lambda x: x[0])

    # Build response — return top 10 nearest shops
    shop_results: list[ShopResult] = []
    for dist, shop in shop_distances[:10]:
        products: list[PesticideProduct] = []
        if relevant_product_names is not None:
            # Only show products relevant to the disease
            for prod_name in relevant_product_names:
                if prod_name in shop["products"]:
                    products.append(
                        PesticideProduct(
                            name=prod_name,
                            price_inr=shop["products"][prod_name],
                            availability=True,
                        )
                    )
                else:
                    products.append(
                        PesticideProduct(
                            name=prod_name,
                            price_inr=0,
                            availability=False,
                        )
                    )
        else:
            # No disease filter — show all products
            for prod_name, price in shop["products"].items():
                products.append(
                    PesticideProduct(name=prod_name, price_inr=price, availability=True)
                )

        shop_results.append(
            ShopResult(
                name=shop["name"],
                address=shop["address"],
                distance_km=dist,
                phone=shop["phone"],
                rating=shop["rating"],
                relevant_products=products,
            )
        )

    return NearbyShopsResponse(
        query_location={"latitude": req.latitude, "longitude": req.longitude},
        crop=crop_key,
        disease_filter=disease_filter_name,
        shops_found=len(shop_results),
        shops=shop_results,
    )


@app.post("/protein-engineering-link", response_model=ProteinEngineeringResponse)
async def protein_engineering_link(req: ProteinEngineeringRequest):
    """Link a crop disease to protein engineering research for developing resistant varieties."""
    crop_key = req.crop.strip().lower()
    if crop_key not in CROP_DISEASES:
        supported = ", ".join(sorted(CROP_DISEASES.keys()))
        raise HTTPException(
            status_code=400,
            detail=f"Crop '{req.crop}' not found in knowledge base. Supported crops: {supported}",
        )

    # Look up disease in the knowledge base
    disease_record = _find_disease_in_kb(req.disease_name, crop_key)
    if disease_record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Disease '{req.disease_name}' not found for crop '{crop_key}' in knowledge base.",
        )

    pathogen = disease_record["scientific_name"]

    # Look up protein engineering data
    protein_data = DISEASE_PROTEIN_MAP.get(disease_record["name"])
    if protein_data is None:
        # Try case-insensitive lookup
        for key, val in DISEASE_PROTEIN_MAP.items():
            if key.lower() == disease_record["name"].lower():
                protein_data = val
                break

    if protein_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No protein engineering data available for disease '{disease_record['name']}'.",
        )

    pathogen_type = protein_data["pathogen_type"]
    target_proteins = [
        TargetProtein(gene=tp["gene"], protein=tp["protein"], function=tp["function"])
        for tp in protein_data["target_proteins"]
    ]
    research_status = protein_data["research_status"]
    engineering_approach = protein_data["engineering_approach"]

    # Build the primary target protein name for the message
    primary_gene = protein_data["target_proteins"][0]["gene"]
    primary_protein = protein_data["target_proteins"][0]["protein"]

    protein_engineering_url = "http://localhost:8007"

    message = (
        f"This disease is caused by {pathogen_type} {pathogen}. "
        f"Developing a resistant variety targeting {primary_gene} ({primary_protein}). "
        f"Our Protein Engineering module can help design resistance proteins. "
        f"Current status: {research_status}."
    )

    return ProteinEngineeringResponse(
        disease_name=disease_record["name"],
        crop=crop_key,
        pathogen=pathogen,
        pathogen_type=pathogen_type,
        target_proteins=target_proteins,
        research_status=research_status,
        engineering_approach=engineering_approach,
        protein_engineering_service_link=protein_engineering_url,
        message=message,
    )


if __name__ == "__main__":
    uvicorn.run(
        "services.fasal_rakshak.app:app", host="0.0.0.0", port=8003, reload=True
    )
