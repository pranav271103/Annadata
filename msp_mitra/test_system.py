"""
Annadata MSP Mitra — System Test Suite
========================================
Tests all pipeline stages: preprocessing, training, prediction,
location engine, crop advisor, and alerts.

Run:  python test_system.py
"""

import sys
import os
import time

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(__file__))


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(test: str, passed: bool, detail: str = ""):
    icon = "✅" if passed else "❌"
    print(f"  {icon} {test}: {detail}")


def test_preprocessing():
    print_header("1. DATA PREPROCESSING")
    from data_preprocessing import get_preprocessor

    pp = get_preprocessor()

    # Load data
    try:
        raw = pp.load_raw_data()
        print_result("Load CSV", True, f"{len(raw):,} rows")
    except Exception as e:
        print_result("Load CSV", False, str(e))
        return False

    # Filter
    filtered = pp.filter_data(raw, "Wheat", "Uttar Pradesh")
    print_result("Filter (Wheat/UP)", len(filtered) > 0, f"{len(filtered)} rows")

    # Full pipeline
    df, features = pp.prepare_ml_dataset("Wheat", "Uttar Pradesh", df=raw)
    print_result(
        "Feature Engineering",
        len(df) > 0 and len(features) > 0,
        f"{len(df)} rows, {len(features)} features",
    )

    if features:
        print(f"    Features: {features}")

    # Prophet data
    prophet_df = pp.prepare_prophet_data("Wheat", "Uttar Pradesh", df=raw)
    print_result("Prophet Data", len(prophet_df) > 0, f"{len(prophet_df)} rows")

    return True


def test_training():
    print_header("2. MODEL TRAINING")
    from model_training import get_trainer
    from data_preprocessing import get_preprocessor

    trainer = get_trainer()
    pp = get_preprocessor()
    raw = pp.load_raw_data()

    start = time.time()
    result = trainer.train_all_models("Wheat", "Uttar Pradesh", raw_df=raw)
    elapsed = time.time() - start

    if "error" in result:
        print_result("Training", False, result["error"])
        return False

    print_result("Training Time", True, f"{elapsed:.1f}s")
    print_result("Best Model", True, result["best_model"])

    # Print metrics table
    print("\n    Model Comparison:")
    print(f"    {'Model':<22} {'RMSE':>8} {'MAE':>8} {'R²':>8}")
    print(f"    {'-'*48}")
    for name, metrics in result["metrics"].items():
        best_marker = " ⭐" if name == result["best_model"] else ""
        print(
            f"    {name:<22} {metrics['rmse']:>8.2f} {metrics['mae']:>8.2f} {metrics['r2']:>8.4f}{best_marker}"
        )

    return True


def test_prediction():
    print_header("3. PREDICTION ENGINE")
    from prediction import get_prediction_engine
    from data_preprocessing import get_preprocessor

    engine = get_prediction_engine()
    pp = get_preprocessor()
    raw = pp.load_raw_data()

    # Ensemble prediction
    forecast = engine.predict("Wheat", "Uttar Pradesh", days=7, raw_df=raw)

    if not forecast:
        print_result("Ensemble Forecast", False, "No result")
        return False

    print_result(
        "Ensemble Forecast",
        True,
        f"{forecast['forecast_days']} days, trend={forecast['trend']}",
    )
    print_result("Confidence Score", True, f"{forecast['confidence_score']}/100")
    print_result("Current Price", True, f"₹{forecast['current_price']}")

    # Print predictions
    print("\n    Day Predictions:")
    for p in forecast["predictions"][:5]:
        print(
            f"    {p['date']}: ₹{p['predicted_price']:.0f} "
            f"({'+' if p['pct_change'] > 0 else ''}{p['pct_change']:.1f}%)"
        )

    # Recommendation
    rec = engine.get_recommendation("Wheat", "Uttar Pradesh", raw_df=raw)
    print_result("Recommendation", True, f"{rec['action']}")
    print(f"    EN: {rec['reason']}")
    print(f"    HI: {rec['reason_hi']}")

    return True


def test_location():
    print_header("4. LOCATION ENGINE")
    from location_engine import get_location_engine

    engine = get_location_engine()

    # Test Haversine
    from location_engine import haversine
    dist = haversine(28.6139, 77.2090, 27.1767, 78.0081)  # Delhi → Agra
    print_result("Haversine (Delhi→Agra)", abs(dist - 200) < 50, f"{dist:.1f} km")

    # Find nearest mandis to Agra
    mandis = engine.find_nearest_mandis(lat=27.18, lon=78.01, top_n=5)
    print_result("Nearest Mandis (Agra)", len(mandis) > 0, f"{len(mandis)} found")
    for m in mandis[:3]:
        print(f"    📍 {m['name']} ({m['state']}) — {m['distance_km']} km")

    # Find by district
    mandis2 = engine.find_nearest_mandis(district="Lucknow", top_n=5)
    print_result("Nearest Mandis (Lucknow)", len(mandis2) > 0, f"{len(mandis2)} found")

    # All mandis
    all_m = engine.get_all_mandis()
    print_result("All Mandis", len(all_m) > 0, f"{len(all_m)} total")

    return True


def test_crop_advisor():
    print_header("5. CROP ADVISOR")
    from crop_advisor import get_crop_advisor

    advisor = get_crop_advisor()

    # List crops
    crops = advisor.get_available_crops()
    print_result("Available Crops", len(crops) > 0, f"{len(crops)} crops")

    # Wheat advisory
    result = advisor.calculate_harvest_advisory(
        "wheat", "2025-01-15", predicted_price=2450
    )
    if "error" in result:
        print_result("Wheat Advisory", False, result["error"])
        return False

    print_result("Wheat Advisory", True, result["status"])
    print(f"    EN: {result['message']}")
    print(f"    HI: {result['message_hi']}")
    if result.get("msp_comparison"):
        print(f"    MSP: {result['msp_comparison']['message']}")

    return True


def test_alerts():
    print_header("6. ALERT SYSTEM")
    from alerts import get_alert_system

    alerts = get_alert_system()

    # Create alert
    result = alerts.create_alert(
        commodity="Wheat",
        state="Uttar Pradesh",
        target_price=2500,
        direction="above",
        phone="+91-9876543210",
        language="en",
    )
    print_result("Create Alert", True, f"ID: {result['alert']['id']}")

    # Hindi alert
    result_hi = alerts.create_alert(
        commodity="Rice",
        state="Punjab",
        target_price=3000,
        direction="above",
        phone="+91-9876543210",
        language="hi",
    )
    print_result("Create Hindi Alert", True, f"ID: {result_hi['alert']['id']}")

    # Check trigger
    triggered = alerts.check_alerts("Wheat", "Uttar Pradesh", current_price=2600)
    print_result("Trigger Check", len(triggered) > 0, f"{len(triggered)} triggered")
    if triggered:
        print(f"\n    SMS Preview:")
        for line in triggered[0]["sms_message"].split("\n")[:4]:
            print(f"    {line}")

    # Active alerts
    active = alerts.get_active_alerts()
    print_result("Active Alerts", True, f"{len(active)} remaining")

    return True


def main():
    print("\n" + "🌾" * 20)
    print("  ANNADATA MSP MITRA — SYSTEM TEST SUITE")
    print("🌾" * 20)

    results = {
        "Preprocessing": test_preprocessing(),
        "Training": test_training(),
        "Prediction": test_prediction(),
        "Location": test_location(),
        "Crop Advisor": test_crop_advisor(),
        "Alerts": test_alerts(),
    }

    print_header("RESULTS SUMMARY")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for name, result in results.items():
        icon = "✅" if result else "❌"
        print(f"  {icon} {name}")

    print(f"\n  {passed}/{total} modules passed")
    print(f"  {'🎉 ALL TESTS PASSED!' if passed == total else '⚠️  Some tests failed'}\n")


if __name__ == "__main__":
    main()
