"""
Data ingestion module for agricultural data collection and processing.

This module provides functionality to collect, process, and manage weather data
specifically optimized for agricultural analysis and crop yield prediction.
"""

from pathlib import Path
from typing import List, Tuple, Dict, Optional
import pandas as pd

from .weather_api import WeatherDataCollector

# Make the main class directly importable from the package
__all__ = [
    'WeatherDataCollector',
]

# Package version
__version__ = '0.1.0'