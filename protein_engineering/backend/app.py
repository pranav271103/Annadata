"""
Protein Engineering Agriculture API - FastAPI Backend
No database dependencies - uses CSV files directly
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
import os
from pathlib import Path

# Initialize FastAPI
app = FastAPI(
    title="Protein Engineering Agriculture API",
    description="AI-powered crop protein engineering with climate integration",
    version="1.0.0"
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Pydantic Models
# ============================================================

class TraitEngineering(BaseModel):
    crop: str
    region: str
    season: str
    drought_tolerance: float  # 0-100
    heat_resistance: float    # 0-100
    disease_resistance: float # 0-100
    salinity_resistance: float # 0-100
    photosynthesis_efficiency: float  # 0-100
    nitrogen_efficiency: float  # 0-100

# ============================================================
# Data Loading Engine (CSV-based, NO DATABASE)
# ============================================================

class AgriculturalDataEngine:
    def __init__(self):
        self.weather_data = None
        self.crop_data = None
        self.data_dir = Path(__file__).parent / "data"
        self.load_data()
        
    def load_data(self):
        """Load weather and crop data from CSV files"""
        try:
            weather_path = self.data_dir / "weather_processed.csv"
            crop_path = self.data_dir / "crop_raw_data.csv"
            
            if weather_path.exists():
                self.weather_data = pd.read_csv(weather_path)
                print(f"✓ Weather data loaded: {len(self.weather_data)} records")
            else:
                print(f"⚠ Weather data not found at {weather_path}")
            
            if crop_path.exists():
                self.crop_data = pd.read_csv(crop_path)
                print(f"✓ Crop data loaded: {len(self.crop_data)} records")
            else:
                print(f"⚠ Crop data not found at {crop_path}")
                
        except Exception as e:
            print(f"❌ Error loading data: {e}")
    
    def get_regional_climate_profile(self, region: str) -> Dict:
        """Extract climate profile for a region from weather data"""
        if self.weather_data is None:
            return {
                'region': region,
                'avg_temperature': 25.0,
                'avg_humidity': 65.0,
                'avg_rainfall': 1000.0,
                'avg_wind_speed': 3.5,
                'temp_range': 20.0,
                'extreme_weather_events': {
                    'rainy_days': 50,
                    'thunderstorms': 10,
                    'clear_days': 200
                },
                'note': 'Using default values - CSV not loaded'
            }
        
        # Try exact match first
        region_weather = self.weather_data[
            self.weather_data['region_name'] == region
        ]
        
        # If no exact match, try partial match (case-insensitive)
        if region_weather.empty:
            region_weather = self.weather_data[
                self.weather_data['region_name'].str.contains(region, case=False, na=False)
            ]
        
        # If still no match, use all data as fallback
        if region_weather.empty:
            print(f"⚠ No weather data for {region}, using aggregate data")
            region_weather = self.weather_data
        
        profile = {
            'region': region,
            'avg_temperature': float(region_weather['temperature_current'].mean()),
            'avg_humidity': float(region_weather['humidity_relative_humidity'].mean()),
            'avg_rainfall': float(region_weather['precipitation_rain_1h'].mean()),
            'avg_wind_speed': float(region_weather['wind_speed'].mean()),
            'temp_range': float(
                region_weather['temperature_max'].max() - 
                region_weather['temperature_min'].min()
            ),
            'extreme_weather_events': {
                'rainy_days': int(region_weather['extreme_weather_is_rainy'].sum()),
                'thunderstorms': int(region_weather['extreme_weather_is_thunderstorm'].sum()),
                'clear_days': int(region_weather['extreme_weather_is_clear'].sum()),
            },
            'samples': len(region_weather)
        }
        return profile
    
    def get_crop_performance(self, crop: str, state: str, season: str) -> Dict:
        """Get historical crop performance metrics"""
        if self.crop_data is None:
            return {
                'crop': crop,
                'avg_yield': 2.5,
                'max_yield': 5.0,
                'min_yield': 1.0,
                'avg_fertilizer': 1000000.0,
                'avg_pesticide': 5000.0,
                'avg_rainfall': 1200.0,
                'years_data': 10,
                'samples': 100,
                'note': 'Using default values - CSV not loaded'
            }
        
        # Try exact match
        crop_filter = self.crop_data[
            (self.crop_data['Crop'].str.lower() == crop.lower()) &
            (self.crop_data['State'].str.lower() == state.lower()) &
            (self.crop_data['Season'].str.strip().str.lower() == season.lower())
        ]
        
        # If no exact match, try crop + state only
        if crop_filter.empty:
            crop_filter = self.crop_data[
                (self.crop_data['Crop'].str.lower() == crop.lower()) &
                (self.crop_data['State'].str.lower() == state.lower())
            ]
        
        # If still no match, try crop only
        if crop_filter.empty:
            crop_filter = self.crop_data[
                self.crop_data['Crop'].str.lower() == crop.lower()
            ]
        
        # If still no match, use all data
        if crop_filter.empty:
            print(f"⚠ No crop data for {crop} in {state} ({season}), using aggregate")
            crop_filter = self.crop_data
        
        performance = {
            'crop': crop,
            'avg_yield': float(crop_filter['Yield'].mean()),
            'max_yield': float(crop_filter['Yield'].max()),
            'min_yield': float(crop_filter['Yield'].min()),
            'avg_fertilizer': float(crop_filter['Fertilizer'].mean()),
            'avg_pesticide': float(crop_filter['Pesticide'].mean()),
            'avg_rainfall': float(crop_filter['Annual_Rainfall'].mean()),
            'years_data': int(crop_filter['Crop_Year'].nunique()),
            'samples': len(crop_filter)
        }
        return performance

# Initialize data engine globally
data_engine = AgriculturalDataEngine()

# ============================================================
# Trait-to-Protein Mapping Database (In-Memory)
# ============================================================

# ============================================================
# Trait-to-Protein Mapping Database (VALID PDB IDs)
# ============================================================

TRAIT_PROTEIN_MAPPING = {
    'drought_tolerance': {
        'proteins': ['ABA2', 'NCEDs', 'PP2Cs', 'SnRK2s'],
        'pdb_ids': ['1RCX', '3WU2', '2P2A', '3UC3'],  # FIXED: Valid PDB IDs
        'mechanism': 'Abscisic acid signaling pathway',
        'genes': ['NCED3', 'PP2C', 'SnRK2.2', 'ABA2'],
        'yield_impact': 15
    },
    'heat_resistance': {
        'proteins': ['HSP70', 'HSP90', 'ROP2', 'WRKY26'],
        'pdb_ids': ['1HJO', '1YET', '2P1N', '1YRG'],  # FIXED: Valid PDB IDs
        'mechanism': 'Heat shock protein activation',
        'genes': ['HSP70', 'HSP90', 'ROP2', 'WRKY26'],
        'yield_impact': 12
    },
    'disease_resistance': {
        'proteins': ['R-genes', 'NBS-LRR', 'PAMP-receptors', 'WRKY'],
        'pdb_ids': ['4KXF', '4M7A', '3JL7', '2AYD'],  # FIXED: Valid PDB IDs
        'mechanism': 'Pathogen resistance signaling',
        'genes': ['R1', 'NBS-LRR', 'FLS2', 'WRKY45'],
        'yield_impact': 20
    },
    'salinity_resistance': {
        'proteins': ['Na+/H+ antiporter', 'SOS1', 'SOS2', 'SOS3'],
        'pdb_ids': ['1ZCD', '4BYG', '3UC4', '2O0X'],  # FIXED: Valid PDB IDs
        'mechanism': 'Ion homeostasis regulation',
        'genes': ['NHX1', 'SOS1', 'SOS2', 'SOS3'],
        'yield_impact': 18
    },
    'photosynthesis_efficiency': {
        'proteins': ['Rubisco', 'Photosystem II', 'Cytochrome b6f', 'ATP Synthase'],
        'pdb_ids': ['1RCX', '3WU2', '2E74', '1C0V'],  # FIXED: Valid PDB IDs (Rubisco, PSII, Cytb6f, ATPase)
        'mechanism': 'Photosynthetic pathway optimization',
        'genes': ['rbcL', 'psbA', 'petB', 'atpH'],
        'yield_impact': 25
    },
    'nitrogen_efficiency': {
        'proteins': ['Nitrate reductase', 'Nitrite reductase', 'Glutamine synthetase', 'GOGAT'],
        'pdb_ids': ['1SIR', '1NIR', '2GLS', '1LLW'],  # FIXED: Valid PDB IDs
        'mechanism': 'Nitrogen assimilation pathway',
        'genes': ['NR', 'NiR', 'GS1', 'GOGAT'],
        'yield_impact': 22
    }
}

# ============================================================
# API Endpoints
# ============================================================

@app.get("/")
async def root():
    """API root endpoint with available routes"""
    return {
        "message": "Protein Engineering Agriculture API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "climate_profile": "/climate/{region}",
            "crop_performance": "/crop-performance/{crop}/{state}/{season}",
            "protein_traits": "/protein-traits/{trait}",
            "trait_engineering": "/engineer-trait",
            "recommendations": "/recommendations?crop=X&region=Y&season=Z"
        },
        "data_status": {
            "weather_loaded": data_engine.weather_data is not None,
            "crop_loaded": data_engine.crop_data is not None
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "weather_data": data_engine.weather_data is not None,
        "crop_data": data_engine.crop_data is not None
    }

@app.get("/climate/{region}")
async def get_climate_profile(region: str):
    """Get climate profile for a region"""
    profile = data_engine.get_regional_climate_profile(region)
    return profile

@app.get("/crop-performance/{crop}/{state}/{season}")
async def get_crop_perf(crop: str, state: str, season: str):
    """Get crop performance metrics"""
    perf = data_engine.get_crop_performance(crop, state, season)
    return perf

@app.get("/protein-traits/{trait}")
async def get_protein_trait(trait: str):
    """Get protein information for a specific trait"""
    if trait not in TRAIT_PROTEIN_MAPPING:
        raise HTTPException(
            status_code=404,
            detail=f"Trait '{trait}' not found. Available: {list(TRAIT_PROTEIN_MAPPING.keys())}"
        )
    return {
        'trait': trait,
        'data': TRAIT_PROTEIN_MAPPING[trait]
    }

@app.post("/engineer-trait")
async def engineer_trait(config: TraitEngineering):
    """Process trait engineering request with climate context"""
    
    # Get climate profile
    climate = data_engine.get_regional_climate_profile(config.region)
    
    # Get crop performance
    crop_perf = data_engine.get_crop_performance(
        config.crop, 
        config.region, 
        config.season
    )
    
    # Compile trait selections
    selected_traits = {}
    trait_configs = {
        'drought_tolerance': config.drought_tolerance,
        'heat_resistance': config.heat_resistance,
        'disease_resistance': config.disease_resistance,
        'salinity_resistance': config.salinity_resistance,
        'photosynthesis_efficiency': config.photosynthesis_efficiency,
        'nitrogen_efficiency': config.nitrogen_efficiency,
    }
    
    for trait, value in trait_configs.items():
        if value > 0:
            selected_traits[trait] = value
    
    # Calculate combined yield impact
    total_yield_impact = 0
    recommended_proteins = []
    
    for trait, intensity in selected_traits.items():
        if trait in TRAIT_PROTEIN_MAPPING:
            trait_data = TRAIT_PROTEIN_MAPPING[trait]
            contribution = (intensity / 100.0) * trait_data['yield_impact']
            total_yield_impact += contribution
            
            recommended_proteins.append({
                'trait': trait,
                'intensity': intensity,
                'proteins': trait_data['proteins'],
                'pdb_ids': trait_data['pdb_ids'],
                'genes': trait_data['genes'],
                'mechanism': trait_data['mechanism'],
                'yield_contribution': round(contribution, 2)
            })
    
    # Cap yield improvement at realistic value (50%)
    total_yield_impact = min(total_yield_impact, 50)
    
    # Get baseline yield
    baseline_yield = crop_perf.get('avg_yield', 2.5)
    projected_yield = baseline_yield * (1 + total_yield_impact / 100)
    
    return {
        'crop': config.crop,
        'region': config.region,
        'season': config.season,
        'climate_context': climate,
        'baseline_yield': round(baseline_yield, 2),
        'projected_yield': round(projected_yield, 2),
        'yield_increase_percent': round(total_yield_impact, 2),
        'selected_traits': selected_traits,
        'recommended_proteins': recommended_proteins,
        'climate_resilience_score': calculate_resilience_score(config, climate),
        'feasibility_score': calculate_feasibility(config),
        'recommendations': generate_recommendations(config, climate, crop_perf)
    }

@app.get("/recommendations")
async def get_recommendations(crop: str, region: str, season: str):
    """Get trait engineering recommendations based on climate"""
    climate = data_engine.get_regional_climate_profile(region)
    crop_perf = data_engine.get_crop_performance(crop, region, season)
    
    recommendations = {
        'crop': crop,
        'region': region,
        'season': season,
        'climate_analysis': analyze_climate_stress(climate),
        'priority_traits': prioritize_traits_by_climate(climate),
        'crop_baseline': crop_perf,
        'optimal_trait_combination': generate_optimal_combination(climate, crop_perf)
    }
    
    return recommendations

# ============================================================
# Helper Functions
# ============================================================

def calculate_resilience_score(config: TraitEngineering, climate: Dict) -> float:
    """Calculate climate resilience score (0-100)"""
    score = 50.0
    
    score += config.drought_tolerance * 0.15
    score += config.heat_resistance * 0.2
    score += config.disease_resistance * 0.15
    score += config.salinity_resistance * 0.1
    
    if climate:
        if climate.get('avg_temperature', 0) > 30:
            score += config.heat_resistance * 0.1
        if climate.get('avg_rainfall', 0) < 1000:
            score += config.drought_tolerance * 0.1
    
    return min(100.0, score)

def calculate_feasibility(config: TraitEngineering) -> float:
    """Calculate genetic modification feasibility (0-100)"""
    trait_count = sum(1 for v in [
        config.drought_tolerance,
        config.heat_resistance,
        config.disease_resistance,
        config.salinity_resistance,
        config.photosynthesis_efficiency,
        config.nitrogen_efficiency
    ] if v > 50)
    
    base_feasibility = 80
    feasibility = base_feasibility - (trait_count * 10)
    return max(30.0, min(100.0, feasibility))

def analyze_climate_stress(climate: Dict) -> Dict:
    """Analyze climate stressors based on weather data"""
    if not climate:
        return {}
    
    avg_temp = climate.get('avg_temperature', 25)
    avg_rain = climate.get('avg_rainfall', 1000)
    avg_wind = climate.get('avg_wind_speed', 3)
    thunderstorms = climate.get('extreme_weather_events', {}).get('thunderstorms', 0)
    
    stressors = {
        'temperature_stress': 'High' if avg_temp > 30 else 'Moderate' if avg_temp > 20 else 'Low',
        'water_stress': 'High' if avg_rain < 800 else 'Moderate' if avg_rain < 1200 else 'Low',
        'wind_stress': 'High' if avg_wind > 5 else 'Low',
        'extreme_events': 'Frequent' if thunderstorms > 20 else 'Occasional'
    }
    return stressors

def prioritize_traits_by_climate(climate: Dict) -> List[str]:
    """Prioritize traits based on climate conditions"""
    priorities = []
    
    if climate:
        avg_temp = climate.get('avg_temperature', 25)
        avg_rain = climate.get('avg_rainfall', 1000)
        avg_wind = climate.get('avg_wind_speed', 3)
        rainy_days = climate.get('extreme_weather_events', {}).get('rainy_days', 0)
        
        if avg_temp > 28:
            priorities.append('heat_resistance')
        if avg_rain < 1000:
            priorities.append('drought_tolerance')
        if avg_wind > 4:
            priorities.append('structural_resilience')
        if rainy_days > 100:
            priorities.append('disease_resistance')
    
    if not priorities:
        priorities = ['photosynthesis_efficiency', 'nitrogen_efficiency']
    
    return priorities

def generate_optimal_combination(climate: Dict, crop_perf: Dict) -> Dict:
    """Generate optimal trait combination"""
    priorities = prioritize_traits_by_climate(climate)
    return {
        'primary_trait': priorities[0] if priorities else 'photosynthesis_efficiency',
        'secondary_traits': priorities[1:3] if len(priorities) > 1 else ['nitrogen_efficiency'],
        'rationale': 'Combination tailored to local climate and crop baseline performance'
    }

def generate_recommendations(config: TraitEngineering, climate: Dict, crop_perf: Dict) -> List[str]:
    """Generate actionable recommendations"""
    recommendations = []
    
    avg_temp = climate.get('avg_temperature', 25)
    avg_rain = climate.get('avg_rainfall', 1000)
    
    if config.drought_tolerance > 70 and avg_rain < 1000:
        recommendations.append("High drought tolerance is critical for this region's low rainfall")
    
    if config.heat_resistance > 70 and avg_temp > 28:
        recommendations.append("Heat resistance engineering is optimal given rising temperatures")
    
    if config.disease_resistance > 70:
        recommendations.append("Strong disease resistance recommended due to high fungal/bacterial pressure in monsoon regions")
    
    if config.photosynthesis_efficiency > 80:
        recommendations.append("Photosynthesis optimization will provide consistent yield improvements across all climates")
    
    if config.nitrogen_efficiency > 70:
        recommendations.append("Nitrogen efficiency reduces fertilizer dependency and environmental impact")
    
    return recommendations if recommendations else ["General trait enhancement recommended for yield improvement"]

# ============================================================
# Run Server
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)