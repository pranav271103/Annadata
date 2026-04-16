import sys
import os
from pathlib import Path

# Add the project root and msp_mitra to sys.path
root = Path(r"c:\Users\prana\Downloads\Annadata\Annadata")
msp_mitra_dir = root / "msp_mitra"
sys.path.insert(0, str(msp_mitra_dir))

print(f"Testing data_loader at {msp_mitra_dir}...")

try:
    from data_loader import get_price_loader
    loader = get_price_loader()
    if loader.df is not None and not loader.df.empty:
        print(f"SUCCESS: Loaded {len(loader.df)} records")
        print(f"Commodities: {loader.commodities[:5]}...")
    else:
        print("FAILED: Dataframe is empty or None")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
