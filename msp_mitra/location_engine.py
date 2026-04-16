"""
Annadata MSP Mitra — Location-Based Mandi Recommendation Engine
================================================================
Uses Haversine formula to find nearest mandis and ranks them by a
composite score: (predicted_price * 0.7) - (distance_km * 0.3).
"""

import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
MANDI_CSV = DATA_DIR / "mandi_master.csv"

# ---- Indian district approximate coordinates (fallback) ----
# Only major districts — for full coverage, geocoding API would be used
DISTRICT_COORDS: Dict[str, Tuple[float, float]] = {
    "agra": (27.1767, 78.0081),
    "lucknow": (26.8467, 80.9462),
    "kanpur": (26.4499, 80.3319),
    "varanasi": (25.3176, 82.9739),
    "jaipur": (26.9124, 75.7873),
    "jodhpur": (26.2389, 73.0243),
    "bhopal": (23.2599, 77.4126),
    "indore": (22.7196, 75.8577),
    "pune": (18.5204, 73.8567),
    "nagpur": (21.1458, 79.0882),
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090),
    "chennai": (13.0827, 80.2707),
    "hyderabad": (17.3850, 78.4867),
    "kolkata": (22.5726, 88.3639),
    "patna": (25.5941, 85.1376),
    "ahmedabad": (23.0225, 72.5714),
    "chandigarh": (30.7333, 76.7794),
    "dehradun": (30.3165, 78.0322),
    "shimla": (31.1048, 77.1734),
    "guwahati": (26.1445, 91.7362),
    "ranchi": (23.3441, 85.3096),
    "bhubaneswar": (20.2961, 85.8245),
    "raipur": (21.2514, 81.6296),
    "prayagraj": (25.4358, 81.8463),
    "meerut": (28.9845, 77.7064),
    "gorakhpur": (26.7606, 83.3732),
    "aligarh": (27.88, 78.08),
    "mathura": (27.4924, 77.6737),
    "bareilly": (28.367, 79.4304),
    "ludhiana": (30.901, 75.8573),
    "amritsar": (31.634, 74.8723),
    "karnal": (29.6857, 76.9905),
    "hisar": (29.1492, 75.7217),
    "kota": (25.2138, 75.8648),
    "ujjain": (23.1765, 75.7885),
    "mandsaur": (24.0713, 75.0662),
    "surat": (21.1702, 72.8311),
    "rajkot": (22.3039, 70.8022),
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance (km) between two points
    on Earth using the Haversine formula.
    """
    R = 6371  # Earth radius in km

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))

    return R * c


class LocationEngine:
    """Find and rank nearest mandis by distance and predicted price."""

    def __init__(self):
        self.mandis: pd.DataFrame = pd.DataFrame()
        self._load_mandi_data()

    def _load_mandi_data(self):
        """Load mandi master CSV with coordinates."""
        if not MANDI_CSV.exists():
            logger.warning(f"Mandi data not found: {MANDI_CSV}")
            return

        try:
            self.mandis = pd.read_csv(MANDI_CSV)
            # Ensure lat/lon are numeric
            self.mandis["latitude"] = pd.to_numeric(
                self.mandis["latitude"], errors="coerce"
            )
            self.mandis["longitude"] = pd.to_numeric(
                self.mandis["longitude"], errors="coerce"
            )
            self.mandis = self.mandis.dropna(subset=["latitude", "longitude"])
            logger.info(f"Loaded {len(self.mandis)} mandis with coordinates")
        except Exception as e:
            logger.error(f"Failed to load mandi data: {e}")

    def resolve_location(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        district: Optional[str] = None,
    ) -> Tuple[float, float]:
        """
        Resolve user location to lat/lon.
        Priority: explicit coords > district lookup.
        """
        if lat is not None and lon is not None:
            return float(lat), float(lon)

        if district:
            key = district.strip().lower().replace(" ", "")
            # Check district coords lookup
            for k, v in DISTRICT_COORDS.items():
                if k in key or key in k:
                    return v

            # Try matching against mandi data
            match = self.mandis[
                self.mandis["district"].str.lower().str.contains(
                    district.lower(), na=False
                )
            ]
            if not match.empty:
                row = match.iloc[0]
                return float(row["latitude"]), float(row["longitude"])

        raise ValueError(
            "Could not resolve location. Provide lat/lon or a valid district name."
        )

    def find_nearest_mandis(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        district: Optional[str] = None,
        top_n: int = 10,
        max_radius_km: float = 500,
        predicted_prices: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find nearest mandis ranked by composite score.

        Args:
            lat, lon: User coordinates
            district: District name (fallback for lat/lon)
            top_n: Number of results
            max_radius_km: Maximum search radius
            predicted_prices: {mandi_name: predicted_price} for ranking

        Returns:
            List of mandi dicts sorted by score
        """
        if self.mandis.empty:
            return []

        user_lat, user_lon = self.resolve_location(lat, lon, district)

        # Calculate distance for each mandi
        results = []
        for _, mandi in self.mandis.iterrows():
            dist = haversine(
                user_lat, user_lon,
                float(mandi["latitude"]),
                float(mandi["longitude"]),
            )

            if dist > max_radius_km:
                continue

            mandi_name = str(mandi.get("name", "Unknown"))
            mandi_city = str(mandi.get("city", ""))
            mandi_state = str(mandi.get("state", ""))
            mandi_district = str(mandi.get("district", ""))

            # Get predicted price if available
            pred_price = 0
            if predicted_prices:
                # Try matching mandi name
                for key, price in predicted_prices.items():
                    if (
                        key.lower() in mandi_name.lower()
                        or mandi_name.lower() in key.lower()
                        or key.lower() in mandi_city.lower()
                    ):
                        pred_price = price
                        break

            # Composite score: higher price + closer distance = better
            # Normalize distance (inverse — closer is better)
            dist_score = max(0, 1 - (dist / max_radius_km))
            price_score = pred_price / 10000 if pred_price > 0 else 0

            composite_score = (price_score * 0.7) + (dist_score * 0.3)

            results.append(
                {
                    "name": mandi_name,
                    "city": mandi_city,
                    "district": mandi_district,
                    "state": mandi_state,
                    "latitude": round(float(mandi["latitude"]), 4),
                    "longitude": round(float(mandi["longitude"]), 4),
                    "distance_km": round(dist, 1),
                    "predicted_price": round(pred_price, 2) if pred_price > 0 else None,
                    "commodities": str(mandi.get("commodities", "")),
                    "score": round(composite_score, 4),
                }
            )

        # Sort by composite score (descending) if prices available,
        # otherwise by distance (ascending)
        if predicted_prices:
            results.sort(key=lambda x: x["score"], reverse=True)
        else:
            results.sort(key=lambda x: x["distance_km"])

        return results[:top_n]

    def get_all_mandis(self) -> List[Dict[str, Any]]:
        """Return all mandis for map display."""
        if self.mandis.empty:
            return []

        return [
            {
                "name": str(row.get("name", "Unknown")),
                "city": str(row.get("city", "")),
                "district": str(row.get("district", "")),
                "state": str(row.get("state", "")),
                "latitude": round(float(row["latitude"]), 4),
                "longitude": round(float(row["longitude"]), 4),
                "commodities": str(row.get("commodities", "")),
            }
            for _, row in self.mandis.iterrows()
        ]


# --------------- Singleton ---------------
_location_engine: Optional[LocationEngine] = None


def get_location_engine() -> LocationEngine:
    global _location_engine
    if _location_engine is None:
        _location_engine = LocationEngine()
    return _location_engine
