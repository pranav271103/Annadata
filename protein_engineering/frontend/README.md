# Protein Engineering for Agriculture

**AI-Powered Crop Optimization with Interactive 3D Protein Visualization**

This module is part of Project Annadata. It provides a platform to explore how modifying crop traits at the protein level can lead to higher yields and better climate resilience.

---

## Features

| Feature | Description |
| :-- | :-- |
| **3D Protein Viewer** | Interactive visualization of protein structures from the RCSB PDB database. Click any atom to inspect its chemical properties. |
| **Trait Engineering** | Configure desired crop traits like Drought Tolerance, Heat Resistance, and Nitrogen Efficiency. |
| **Yield Prediction** | Get AI-powered predictions for yield increase, climate resilience, and implementation feasibility. |
| **Recommendations** | Receive actionable scientific recommendations based on your selected traits and regional climate data. |

---

## Architecture

```
protein_engineering/
├── backend/                # FastAPI Backend
│   ├── app.py              # Main API application
│   ├── data/               # CSV data files (weather, crop)
│   └── requirements.txt    # Python dependencies
│
└── frontend/               # Next.js Frontend
    ├── app/                # Next.js App Router
    │   ├── page.tsx        # Main entry point
    │   └── globals.css     # Global styles
    │
    └── components/         # React Components
        ├── ProteinVisualization.tsx   # 3Dmol.js viewer
        ├── ProteinEngineeringView.tsx # Main dashboard
        ├── ProteinEngineering.tsx     # Trait config form
        └── RecommendationPanel.tsx    # Results display
```

---

## Quick Start

### 1. Start the Backend

```bash
cd protein_engineering/backend
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
The API will be available at `http://localhost:8000`.

### 2. Start the Frontend

```bash
cd protein_engineering/frontend
npm install
npm run dev
```
The UI will be available at `http://localhost:3000`.

---

## API Endpoints

| Method | Endpoint | Description |
| :-- | :-- | :-- |
| `GET` | `/` | API status and available endpoints |
| `GET` | `/health` | Health check |
| `GET` | `/climate/{region}` | Get climate profile for a region |
| `GET` | `/crop-performance/{crop}/{state}/{season}` | Get historical crop performance |
| `GET` | `/protein-traits/{trait}` | Get protein info for a trait |
| `POST` | `/engineer-trait` | Submit trait configuration for analysis |
| `GET` | `/recommendations` | Get trait recommendations for a crop/region |

### Example: `POST /engineer-trait`

**Request Body:**
```json
{
  "crop": "Wheat",
  "region": "Punjab",
  "season": "Rabi",
  "drought_tolerance": 75,
  "heat_resistance": 60,
  "disease_resistance": 50,
  "salinity_resistance": 30,
  "photosynthesis_efficiency": 80,
  "nitrogen_efficiency": 40
}
```

**Response:**
```json
{
  "crop": "Wheat",
  "baseline_yield": 2.5,
  "projected_yield": 3.1,
  "yield_increase_percent": 24.5,
  "climate_resilience_score": 78,
  "feasibility_score": 60,
  "recommended_proteins": [
    {
      "trait": "photosynthesis_efficiency",
      "proteins": ["Rubisco", "Photosystem II"],
      "pdb_ids": ["1RCX", "3WU2"],
      "mechanism": "Photosynthetic pathway optimization"
    }
  ]
}
```

---

## Trait-to-Protein Mapping

The system maps user-selected traits to scientifically relevant proteins and genes.

| Trait | Key Proteins | PDB IDs | Mechanism |
| :-- | :-- | :-- | :-- |
| **Drought Tolerance** | ABA2, NCEDs | `1RCX`, `3WU2` | Abscisic acid signaling |
| **Heat Resistance** | HSP70, HSP90 | `1HJO`, `1YET` | Heat shock protein activation |
| **Disease Resistance** | R-genes, NBS-LRR | `4KXF`, `4M7A` | Pathogen resistance signaling |
| **Salinity Resistance** | SOS1, SOS2 | `1ZCD`, `4BYG` | Ion homeostasis regulation |
| **Photosynthesis Efficiency** | Rubisco, PSII | `1RCX`, `3WU2` | Photosynthetic optimization |
| **Nitrogen Efficiency** | Nitrate Reductase, GS | `1SIR`, `2GLS` | Nitrogen assimilation |

---

## Frontend Components

- **`ProteinVisualization.tsx`**: Renders interactive 3D protein structures using `3Dmol.js`. Supports atom-level click inspection.
- **`ProteinEngineeringView.tsx`**: The main dashboard that orchestrates the trait configuration form, API calls, and results display.
- **`ProteinEngineering.tsx`**: The form component for selecting crop, region, season, and adjusting trait sliders.
- **`RecommendationPanel.tsx`**: Displays the scientific recommendations and protein details returned by the API.

---

## Tech Stack

| Layer | Technology |
| :-- | :-- |
| **Backend** | Python 3.9+, FastAPI, Pandas |
| **Frontend** | Next.js 16, React 18, TypeScript |
| **3D Rendering** | 3Dmol.js |
| **Data Source** | RCSB PDB (for protein structures) |

---

## Data Files

Located in `backend/data/`:

- `weather_processed.csv`: Climate data for regional analysis.
- `crop_raw_data.csv`: Historical crop yield data by state and season.

---

## License

Part of Project Annadata. See the root `LICENSE` file for details.
