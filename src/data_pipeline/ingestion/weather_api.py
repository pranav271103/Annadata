import requests
from typing import Dict, Any, Optional
from src.config.settings import settings

class WeatherDataCollector:
    """
    Collector for fetching weather data from external APIs (e.g., OpenWeatherMap).
    """
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENWEATHER_API_KEY
        
    def get_current_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Fetch current weather data for a specific location.
        """
        if not self.api_key:
            # Return mock data if no API key is present (for development)
            return {
                "main": {"temp": 298.15, "humidity": 60},
                "weather": [{"description": "clear sky"}],
                "mock": True
            }
            
        url = f"{self.BASE_URL}/weather"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
            "units": "metric"
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching weather data: {e}")
            raise
