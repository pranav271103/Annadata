"""
Annadata MSP Mitra — Crop Advisor (Innovation Layer)
=====================================================
Combines crop growth cycle data with price predictions to give
integrated harvest + market advice.

Example output:
  "Your wheat will be ready in 18 days. Expected price: ₹2450/quintal."
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- Crop Growth Cycle Data (days from sowing to harvest) ----
CROP_CYCLES: Dict[str, Dict[str, Any]] = {
    "wheat": {
        "growth_days": 120,
        "sowing_months": [10, 11],  # Oct–Nov (Rabi)
        "harvest_months": [3, 4],   # Mar–Apr
        "season": "Rabi",
        "msp_2024_25": 2275,        # MSP Rs/quintal
        "description": "Winter crop, grown across North India",
        "description_hi": "शीतकालीन फसल, उत्तर भारत में उगाई जाती है",
    },
    "rice": {
        "growth_days": 150,
        "sowing_months": [6, 7],    # Jun–Jul (Kharif)
        "harvest_months": [10, 11], # Oct–Nov
        "season": "Kharif",
        "msp_2024_25": 2300,
        "description": "Monsoon crop, major in eastern & southern India",
        "description_hi": "मानसून फसल, पूर्वी और दक्षिण भारत में प्रमुख",
    },
    "maize": {
        "growth_days": 100,
        "sowing_months": [6, 7],
        "harvest_months": [9, 10],
        "season": "Kharif",
        "msp_2024_25": 2090,
        "description": "Versatile cereal, grown in kharif season",
        "description_hi": "बहुमुखी अनाज, खरीफ में उगाया जाता है",
    },
    "cotton": {
        "growth_days": 180,
        "sowing_months": [4, 5],
        "harvest_months": [10, 11, 12],
        "season": "Kharif",
        "msp_2024_25": 7121,       # Long staple
        "description": "Cash crop, grown in Maharashtra, Gujarat, Punjab",
        "description_hi": "नकदी फसल, महाराष्ट्र, गुजरात, पंजाब में",
    },
    "soybean": {
        "growth_days": 100,
        "sowing_months": [6, 7],
        "harvest_months": [9, 10],
        "season": "Kharif",
        "msp_2024_25": 4892,
        "description": "Oilseed crop, major in Madhya Pradesh",
        "description_hi": "तिलहन फसल, मध्य प्रदेश में प्रमुख",
    },
    "mustard": {
        "growth_days": 130,
        "sowing_months": [10, 11],
        "harvest_months": [2, 3],
        "season": "Rabi",
        "msp_2024_25": 5650,
        "description": "Rabi oilseed, grown in Rajasthan, UP, Haryana",
        "description_hi": "रबी तिलहन, राजस्थान, यूपी, हरियाणा में",
    },
    "gram": {
        "growth_days": 110,
        "sowing_months": [10, 11],
        "harvest_months": [2, 3],
        "season": "Rabi",
        "msp_2024_25": 5440,
        "description": "Pulse crop, Rabi season",
        "description_hi": "दाल फसल, रबी मौसम",
    },
    "potato": {
        "growth_days": 90,
        "sowing_months": [10, 11],
        "harvest_months": [1, 2, 3],
        "season": "Rabi",
        "msp_2024_25": None,  # No MSP for potato
        "description": "Tuber crop, grown across UP, WB, Bihar",
        "description_hi": "कंद फसल, यूपी, पश्चिम बंगाल, बिहार में",
    },
    "onion": {
        "growth_days": 150,
        "sowing_months": [11, 12],
        "harvest_months": [3, 4, 5],
        "season": "Rabi",
        "msp_2024_25": None,
        "description": "Bulb vegetable, major in Maharashtra & MP",
        "description_hi": "बल्ब सब्जी, महाराष्ट्र और मध्य प्रदेश में प्रमुख",
    },
    "bajra": {
        "growth_days": 90,
        "sowing_months": [6, 7],
        "harvest_months": [9, 10],
        "season": "Kharif",
        "msp_2024_25": 2625,
        "description": "Millet crop, grown in arid regions",
        "description_hi": "बाजरा, शुष्क क्षेत्रों में उगाया जाता है",
    },
    "sugarcane": {
        "growth_days": 360,
        "sowing_months": [2, 3],
        "harvest_months": [12, 1, 2, 3],
        "season": "Annual",
        "msp_2024_25": 340,  # FRP per quintal
        "description": "Perennial cash crop, UP, Maharashtra, Karnataka",
        "description_hi": "बारहमासी नकदी फसल, यूपी, महाराष्ट्र, कर्नाटक",
    },
}


class CropAdvisor:
    """Combine crop growth cycles with price predictions."""

    def get_crop_info(self, crop: str) -> Optional[Dict[str, Any]]:
        """Get crop cycle information."""
        key = crop.strip().lower()
        return CROP_CYCLES.get(key)

    def get_available_crops(self) -> List[str]:
        """List all crops with growth data."""
        return list(CROP_CYCLES.keys())

    def calculate_harvest_advisory(
        self,
        crop: str,
        sowing_date: str,  # format: YYYY-MM-DD
        predicted_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Generate harvest + market advisory.

        Args:
            crop: Crop name
            sowing_date: Date of sowing (YYYY-MM-DD)
            predicted_price: Predicted price at harvest time

        Returns:
            Advisory with harvest estimate and price insight.
        """
        crop_info = self.get_crop_info(crop)
        if not crop_info:
            return {
                "error": f"Crop '{crop}' not found. Available: {', '.join(self.get_available_crops())}",
                "available_crops": self.get_available_crops(),
            }

        try:
            sow_date = datetime.strptime(sowing_date, "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD."}

        growth_days = crop_info["growth_days"]
        harvest_date = sow_date + timedelta(days=growth_days)
        today = datetime.now()
        days_remaining = (harvest_date - today).days

        # Status
        if days_remaining < 0:
            status = "READY_TO_HARVEST"
            status_hi = "कटाई के लिए तैयार"
            days_remaining = 0
        elif days_remaining <= 7:
            status = "HARVEST_IMMINENT"
            status_hi = "कटाई निकट है"
        elif days_remaining <= 30:
            status = "APPROACHING_HARVEST"
            status_hi = "कटाई निकट आ रही है"
        else:
            status = "GROWING"
            status_hi = "बढ़ रही है"

        # Growth progress
        days_since_sowing = (today - sow_date).days
        progress_pct = min(100, max(0, (days_since_sowing / growth_days) * 100))

        # MSP comparison
        msp = crop_info.get("msp_2024_25")
        msp_comparison = None
        if msp and predicted_price:
            diff = predicted_price - msp
            diff_pct = (diff / msp) * 100
            if diff > 0:
                msp_comparison = {
                    "status": "ABOVE_MSP",
                    "difference": round(diff, 2),
                    "difference_pct": round(diff_pct, 2),
                    "message": f"₹{diff:.0f} above MSP ({diff_pct:.1f}%)",
                    "message_hi": f"MSP से ₹{diff:.0f} ऊपर ({diff_pct:.1f}%)",
                }
            else:
                msp_comparison = {
                    "status": "BELOW_MSP",
                    "difference": round(diff, 2),
                    "difference_pct": round(diff_pct, 2),
                    "message": f"₹{abs(diff):.0f} below MSP ({abs(diff_pct):.1f}%)",
                    "message_hi": f"MSP से ₹{abs(diff):.0f} नीचे ({abs(diff_pct):.1f}%)",
                }

        # Generate advisory message
        if predicted_price:
            message = (
                f"Your {crop.title()} will be ready "
                f"{'now' if days_remaining == 0 else f'in {days_remaining} days'} "
                f"(~{harvest_date.strftime('%d %b %Y')}). "
                f"Expected price: ₹{predicted_price:.0f}/quintal."
            )
            message_hi = (
                f"आपकी {crop.title()} "
                f"{'अभी' if days_remaining == 0 else f'{days_remaining} दिनों में'} "
                f"तैयार होगी (~{harvest_date.strftime('%d %b %Y')})। "
                f"अपेक्षित कीमत: ₹{predicted_price:.0f}/क्विंटल।"
            )
        else:
            message = (
                f"Your {crop.title()} will be ready "
                f"{'now' if days_remaining == 0 else f'in {days_remaining} days'} "
                f"(~{harvest_date.strftime('%d %b %Y')})."
            )
            message_hi = (
                f"आपकी {crop.title()} "
                f"{'अभी' if days_remaining == 0 else f'{days_remaining} दिनों में'} "
                f"तैयार होगी (~{harvest_date.strftime('%d %b %Y')})।"
            )

        return {
            "crop": crop.title(),
            "sowing_date": sowing_date,
            "harvest_date": harvest_date.strftime("%Y-%m-%d"),
            "days_remaining": days_remaining,
            "growth_days": growth_days,
            "progress_percent": round(progress_pct, 1),
            "status": status,
            "status_hi": status_hi,
            "season": crop_info["season"],
            "msp": msp,
            "predicted_price": round(predicted_price, 2) if predicted_price else None,
            "msp_comparison": msp_comparison,
            "message": message,
            "message_hi": message_hi,
            "crop_info": {
                "description": crop_info["description"],
                "description_hi": crop_info["description_hi"],
                "sowing_months": crop_info["sowing_months"],
                "harvest_months": crop_info["harvest_months"],
            },
        }


# --------------- Singleton ---------------
_advisor: Optional[CropAdvisor] = None


def get_crop_advisor() -> CropAdvisor:
    global _advisor
    if _advisor is None:
        _advisor = CropAdvisor()
    return _advisor
