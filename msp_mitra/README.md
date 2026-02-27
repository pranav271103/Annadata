# MSP Mitra - Quick Start Guide

## 🚀 Running the System

### Backend
```bash
cd msp_mitra/backend

# Install dependencies
pip install -r requirements.txt

# Start the server
python main.py
```

API runs at: `http://localhost:8001`
API Docs: `http://localhost:8001/docs`

### Frontend
```bash
cd msp_mitra/frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend runs at: `http://localhost:5173`

---

## ✨ Features

### Core Analytics
- ✅ Multi-model price predictions (Prophet + Linear Regression + Moving Average)
- ✅ Market health scoring (0-100)
- ✅ Volatility detection (LOW/MODERATE/HIGH/VERY_HIGH)
- ✅ Trend analysis with visual indicators
- ✅ Seasonal pattern recognition
- ✅ AI-generated natural language insights

### Advanced Features  
- ✅ Export data to CSV
- ✅ Compare multiple commodities
- ✅ State-level overview dashboard
- ✅ Price alerts system
- ✅ Bulk recommendations

---

## 📊 API Endpoints Summary

**Total**: 20+ endpoints

### Core Price (8 endpoints)
- GET `/commodities` - List commodities
- GET `/states` - List states
- GET `/markets/{state}` - Markets in state
- GET `/prices/{commodity}/{state}` - Latest prices
- GET `/prices/history/{commodity}` - Historical data
- POST `/train` - Train models
- GET `/predict/{commodity}/{state}` - Predictions
- GET `/recommend/{commodity}/{state}` - Recommendations

### Analytics (6 endpoints)
- GET `/analytics/volatility/{commodity}/{state}`
- GET `/analytics/trends/{commodity}/{state}`
- GET `/analytics/seasonal/{commodity}`
- GET `/analytics/market-comparison/{commodity}/{state}`
- GET `/analytics/top-performers/{state}`
- GET `/analytics/insights/{commodity}/{state}`

### Features (6 endpoints)
- GET `/features/export/prices/{commodity}/{state}`
- GET `/features/compare/commodities/{state}`
- GET `/features/state-overview/{state}`
- GET `/features/price-alerts/check/{commodity}/{state}`
- GET `/features/recommendations/bulk/{state}`

---

## 🎯 Testing the System

### 1. Start Backend
```bash
cd msp_mitra/backend
python main.py
```

### 2. Test API
```bash
# Health check
curl http://localhost:8001/health

# Get commodities
curl http://localhost:8001/commodities

# Get insights
curl "http://localhost:8001/analytics/insights/Wheat/Uttar%20Pradesh"
```

### 3. Start Frontend
```bash
cd msp_mitra/frontend
npm run dev
```

Visit `http://localhost:5173` and:
- Select commodity (e.g., Wheat)
- Select state (e.g., Uttar Pradesh)
- View analytics dashboard
- Check AI insights
- Review market comparison

---

## 📁 Project Structure

```
msp_mitra/
├── backend/
│   ├── main.py                      # FastAPI app
│   ├── data_loader.py               # Data loading + 5 analytics methods
│   ├── price_predictor_enhanced.py  # Multi-model ensemble
│   ├── market_analytics.py          # Market intelligence
│   ├── insights_engine.py           # AI insights
│   ├── features.py                  # Additional features
│   ├── requirements.txt
│   └── models/                      # Trained model cache
│
├── frontend/
│   └── src/
│       ├── App.tsx                  # Main dashboard
│       └── App.css                  # Premium styling
│
├── data/
│   └── (mandi location files - optional)
│
└── agmarknet_india_historical_prices_2024_2025.csv  # 1.1M+ records
```

---

## 💡 Key Innovations

1. **Multi-Model Ensemble**: 3 models combined for better accuracy
2. **Market Health Scoring**: Holistic 0-100 score
3. **AI Natural Language**: Insights anyone can understand
4. **Volatility Intelligence**: Risk-aware recommendations
5. **Seasonal Awareness**: Learns historical patterns
6. **Comprehensive Analytics**: 6 different dimensions

---

## 🎨 Frontend Features

### Dashboard Components
1. **Market Health Card** - Score + status with progress bar
2. **Volatility Meter** - Classification + score
3. **Trend Indicator** - Direction arrows + strength
4. **Current Price Stats** - Average across markets
5. **AI Insights Panel** - Natural language explanations
6. **Advanced Chart** - Historical + predictions with confidence bands
7. **Market Comparison Table** - Top 5 markets with prices
8. **Seasonal Pattern** - Peak/trough months

---

## 🔧 Troubleshooting

### Backend won't start
- Install Prophet: `pip install prophet`
- Install sklearn: `pip install scikit-learn`
- Check Python version >= 3.9

### Frontend errors
- Install dependencies: `npm install`
- Update packages: `npm install axios recharts`
- Check Node version >= 16

### No predictions
- Train model first: POST to `/train`
- Ensure 30+ days of data available
- Check data file path in `data_loader.py`

---

## 📈 Data Requirements

**Minimum**:
- 30 days of historical data for prediction
- At least 1 commodity, 1 state

**Optimal**:
- 90+ days for better accuracy
- Multiple markets for comparison
- Seasonal data (365+ days) for pattern detection

---

## 🚀 Next Enhancements (Future)

- [ ] Real-time data updates
- [ ] Mobile app version
- [ ] WhatsApp/SMS price alerts
- [ ] Multi-language support
- [ ] Farmer community features
- [ ] Weather integration
- [ ] Crop advisory system

---

Made with ❤️ for Indian Farmers
