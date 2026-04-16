"""
Annadata MSP Mitra — Alert System (Mock SMS/WhatsApp)
======================================================
Creates and manages price alerts with bilingual support.
Generates formatted messages ready for SMS/WhatsApp dispatch.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PriceAlert:
    """Represents a single price alert configuration."""

    def __init__(
        self,
        commodity: str,
        state: str,
        target_price: float,
        direction: str = "above",   # "above" or "below"
        phone: str = "",
        language: str = "en",       # "en" or "hi"
        market: Optional[str] = None,
    ):
        self.id = str(uuid4())[:8]
        self.commodity = commodity
        self.state = state
        self.market = market
        self.target_price = target_price
        self.direction = direction  # trigger when price goes above/below target
        self.phone = phone
        self.language = language
        self.created_at = datetime.now()
        self.triggered = False
        self.triggered_at: Optional[datetime] = None
        self.trigger_price: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "commodity": self.commodity,
            "state": self.state,
            "market": self.market,
            "target_price": self.target_price,
            "direction": self.direction,
            "phone": self.phone,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "triggered": self.triggered,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "trigger_price": self.trigger_price,
        }


class AlertSystem:
    """Manage price alerts and generate mock notifications."""

    def __init__(self):
        self.alerts: List[PriceAlert] = []

    def create_alert(
        self,
        commodity: str,
        state: str,
        target_price: float,
        direction: str = "above",
        phone: str = "",
        language: str = "en",
        market: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new price alert."""
        alert = PriceAlert(
            commodity=commodity,
            state=state,
            target_price=target_price,
            direction=direction,
            phone=phone,
            language=language,
            market=market,
        )
        self.alerts.append(alert)
        logger.info(
            f"Alert created: {alert.id} — {commodity} {direction} ₹{target_price}"
        )

        return {
            "status": "created",
            "alert": alert.to_dict(),
            "message": self._format_creation_message(alert),
        }

    def check_alerts(
        self, commodity: str, state: str, current_price: float
    ) -> List[Dict[str, Any]]:
        """Check if any alerts are triggered by current price."""
        triggered = []

        for alert in self.alerts:
            if alert.triggered:
                continue
            if alert.commodity.lower() != commodity.lower():
                continue
            if alert.state.lower() != state.lower():
                continue

            should_trigger = False
            if alert.direction == "above" and current_price >= alert.target_price:
                should_trigger = True
            elif alert.direction == "below" and current_price <= alert.target_price:
                should_trigger = True

            if should_trigger:
                alert.triggered = True
                alert.triggered_at = datetime.now()
                alert.trigger_price = current_price

                notification = self._generate_notification(alert, current_price)
                triggered.append(notification)
                logger.info(
                    f"Alert {alert.id} triggered! {commodity} @ ₹{current_price}"
                )

        return triggered

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Return all active (un-triggered) alerts."""
        return [a.to_dict() for a in self.alerts if not a.triggered]

    def get_all_alerts(self) -> List[Dict[str, Any]]:
        """Return all alerts."""
        return [a.to_dict() for a in self.alerts]

    def delete_alert(self, alert_id: str) -> bool:
        """Delete an alert by ID."""
        for i, alert in enumerate(self.alerts):
            if alert.id == alert_id:
                self.alerts.pop(i)
                return True
        return False

    # ------------------------------------------------------------------
    # Message Formatting
    # ------------------------------------------------------------------
    def _format_creation_message(self, alert: PriceAlert) -> str:
        """Confirmation message when alert is created."""
        if alert.language == "hi":
            return (
                f"✅ अलर्ट बनाया गया!\n"
                f"📦 फसल: {alert.commodity}\n"
                f"📍 राज्य: {alert.state}\n"
                f"💰 लक्ष्य: ₹{alert.target_price:.0f}/क्विंटल "
                f"({'ऊपर' if alert.direction == 'above' else 'नीचे'})\n"
                f"📱 फोन: {alert.phone or 'N/A'}\n"
                f"🆔 ID: {alert.id}"
            )
        else:
            return (
                f"✅ Alert Created!\n"
                f"📦 Crop: {alert.commodity}\n"
                f"📍 State: {alert.state}\n"
                f"💰 Target: ₹{alert.target_price:.0f}/quintal "
                f"({alert.direction})\n"
                f"📱 Phone: {alert.phone or 'N/A'}\n"
                f"🆔 ID: {alert.id}"
            )

    def _generate_notification(
        self, alert: PriceAlert, current_price: float
    ) -> Dict[str, Any]:
        """Generate SMS/WhatsApp-formatted notification."""
        diff = current_price - alert.target_price
        diff_pct = (diff / alert.target_price * 100) if alert.target_price > 0 else 0

        if alert.language == "hi":
            sms = (
                f"🔔 MSP मित्र अलर्ट!\n\n"
                f"📦 {alert.commodity} की कीमत ₹{current_price:.0f}/क्विंटल हो गई है!\n"
                f"🎯 आपका लक्ष्य: ₹{alert.target_price:.0f}\n"
                f"{'📈' if diff > 0 else '📉'} बदलाव: {'+' if diff > 0 else ''}{diff:.0f} "
                f"({'+' if diff_pct > 0 else ''}{diff_pct:.1f}%)\n\n"
                f"💡 सुझाव: {'अभी बेचें! अच्छा मौका है।' if diff > 0 else 'कीमत नीचे आ गई है। सावधानी बरतें।'}\n\n"
                f"— अन्नदाता MSP मित्र 🌾"
            )
            whatsapp = (
                f"🌾 *अन्नदाता MSP मित्र* 🌾\n\n"
                f"*{alert.commodity}* की कीमत अपडेट!\n\n"
                f"💰 वर्तमान कीमत: *₹{current_price:.0f}/क्विंटल*\n"
                f"🎯 आपका लक्ष्य: ₹{alert.target_price:.0f}\n"
                f"{'📈' if diff > 0 else '📉'} {'+' if diff > 0 else ''}{diff_pct:.1f}%\n\n"
                f"{'✅ *अभी बेचने का अच्छा समय!*' if diff > 0 else '⚠️ *कीमत गिरी है। बाजार देखें।*'}\n\n"
                f"📲 अधिक जानकारी: annadata.app"
            )
        else:
            sms = (
                f"🔔 MSP Mitra Alert!\n\n"
                f"📦 {alert.commodity} price is now ₹{current_price:.0f}/quintal!\n"
                f"🎯 Your target: ₹{alert.target_price:.0f}\n"
                f"{'📈' if diff > 0 else '📉'} Change: {'+' if diff > 0 else ''}{diff:.0f} "
                f"({'+' if diff_pct > 0 else ''}{diff_pct:.1f}%)\n\n"
                f"💡 {'Good time to sell!' if diff > 0 else 'Price has dropped. Be cautious.'}\n\n"
                f"— Annadata MSP Mitra 🌾"
            )
            whatsapp = (
                f"🌾 *Annadata MSP Mitra* 🌾\n\n"
                f"*{alert.commodity}* Price Update!\n\n"
                f"💰 Current Price: *₹{current_price:.0f}/quintal*\n"
                f"🎯 Your Target: ₹{alert.target_price:.0f}\n"
                f"{'📈' if diff > 0 else '📉'} {'+' if diff > 0 else ''}{diff_pct:.1f}%\n\n"
                f"{'✅ *Good time to sell!*' if diff > 0 else '⚠️ *Price dropped. Monitor market.*'}\n\n"
                f"📲 More info: annadata.app"
            )

        return {
            "alert_id": alert.id,
            "type": "PRICE_ALERT",
            "commodity": alert.commodity,
            "state": alert.state,
            "current_price": round(current_price, 2),
            "target_price": alert.target_price,
            "direction": alert.direction,
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
            "phone": alert.phone,
            "language": alert.language,
            "sms_message": sms,
            "whatsapp_message": whatsapp,
            "notification": {
                "title": f"{'📈' if diff > 0 else '📉'} {alert.commodity} Price Alert",
                "body": f"₹{current_price:.0f}/qt — Target {'reached' if diff >= 0 else 'breached'}!",
            },
        }


# --------------- Singleton ---------------
_alert_system: Optional[AlertSystem] = None


def get_alert_system() -> AlertSystem:
    global _alert_system
    if _alert_system is None:
        _alert_system = AlertSystem()
    return _alert_system
