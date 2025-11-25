import sys
import os
sys.path.append(os.getcwd())

def check_import(module_name, friendly_name):
    try:
        __import__(module_name)
        return True
    except ImportError as e:
        print(f"⚠️  Missing dependency for {friendly_name}: {e}")
        return False

try:
    print("--- Verifying Config ---")
    # Check dependencies first
    if not check_import('pydantic_settings', 'Config'):
        print("Please run: pip install -r requirements.txt")
        
    try:
        from src.config.settings import settings
        print(f"✅ Config Loaded: {settings.APP_NAME}")
    except ImportError as e:
        print(f"❌ Config Import Failed: {e}")
    except Exception as e:
        print(f"⚠️  Config Loaded with error (likely missing env vars or deps): {e}")

    print("\n--- Verifying API ---")
    if not check_import('fastapi', 'API'):
        print("Skipping API verification due to missing deps.")
    else:
        try:
            from src.api.app import app
            print(f"✅ API Initialized: {app.title}")
        except Exception as e:
            print(f"❌ API Initialization Failed: {e}")
    
    print("\n--- Verifying Data Pipeline ---")
    try:
        from src.data_pipeline.ingestion.weather_api import WeatherDataCollector
        collector = WeatherDataCollector()
        print(f"✅ Weather Collector Initialized")
    except Exception as e:
        print(f"❌ Data Pipeline Failed: {e}")
    
    print("\n🎉 Verification Complete (check for warnings)")
except Exception as e:
    print(f"\n❌ Verification Script Failed: {e}")
    sys.exit(1)
