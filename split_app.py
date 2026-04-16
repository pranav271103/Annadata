import os

APP_PATH = r'c:\Users\prana\Downloads\Annadata\Annadata\services\kisaan_sahayak\app.py'
DATA_PATH = r'c:\Users\prana\Downloads\Annadata\Annadata\services\kisaan_sahayak\data.py'

with open(APP_PATH, 'r', encoding='utf-8') as f:
    lines = f.readlines()

data_lines = [
    "from typing import Any\n",
    "from collections import defaultdict\n",
    "import hashlib\n",
    "import numpy as np\n\n"
]

app_lines = []

# Line numbers from my research (0-indexed in list)
# FARMING_KNOWLEDGE starts at line 137 (index 136) in the CURRENT RESTORED file
# Wait, I need to be careful with line numbers.

current_mode = "app"

for i, line in enumerate(lines):
    # Detect start of large data blocks
    if line.startswith("FARMING_KNOWLEDGE: dict"):
        current_mode = "data"
    elif line.startswith("GOVERNMENT_SCHEMES: list"):
        current_mode = "data"
    elif line.startswith("CROP_CALENDAR: dict"):
        current_mode = "data"
    elif line.startswith("_CROP_ALIASES: dict"):
        current_mode = "data"
    elif line.startswith("PLANTVILLAGE_CLASSES = ["):
        current_mode = "data"
    elif line.startswith("_AGMARKNET_BASE_PRICES: dict"):
        current_mode = "data"
    elif line.startswith("_WEATHER_PATTERNS: dict"):
        current_mode = "data"
        
    # Detect end of blocks (roughly by looking for the next function or major header)
    if line.startswith("async def") or line.startswith("def _") or line.startswith("@app."):
        if not line.startswith("def _get_crop_grounding_context"): # keep this in app for now or data?
             current_mode = "app"

    if current_mode == "data":
        data_lines.append(line)
    else:
        app_lines.append(line)

# Add imports to app_lines
import_idx = 0
for i, line in enumerate(app_lines):
    if line.startswith("from services.shared.db.session"):
        import_idx = i + 1
        break

app_lines.insert(import_idx, "from .data import *\n")

with open(DATA_PATH, 'w', encoding='utf-8') as f:
    f.writelines(data_lines)

with open(APP_PATH + ".tmp", 'w', encoding='utf-8') as f:
    f.writelines(app_lines)

print(f"Split complete. New app size: {len(app_lines)} lines, Data size: {len(data_lines)} lines.")
