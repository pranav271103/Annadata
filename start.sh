#!/bin/bash

# Backend terminal (FastAPI / Uvicorn)
osascript -e 'tell application "Terminal" to do script "cd /Users/ramanmendiratta/Documents/code/Annadata/Annadata/protein_engineering/backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000"'

# Frontend terminal (Next.js / React)
osascript -e 'tell application "Terminal" to do script "cd /Users/ramanmendiratta/Documents/code/Annadata/Annadata/protein_engineering/frontend && npm run dev"'

echo "✅ Both backend and frontend servers started!"
