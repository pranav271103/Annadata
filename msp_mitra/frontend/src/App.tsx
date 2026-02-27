import { useState, useEffect } from 'react';
import axios from 'axios';
import {
  AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer
} from 'recharts';
import './App.css';

const API_BASE = 'http://localhost:8001';

interface MarketHealth {
  score: number;
  status: string;
}

interface Volatility {
  volatility_score: number;
  classification: string;
  mean_price: number;
}

interface Trend {
  trend: string;
  indicator: string;
  color: string;
  strength: number;
  strength_label?: string;
  change_percent: number;
}

function App() {
  // State
  const [commodities, setCommodities] = useState<string[]>([]);
  const [states, setStates] = useState<string[]>([]);
  const [selectedCommodity, setSelectedCommodity] = useState('');
  const [selectedState, setSelectedState] = useState('');

  const [historicalData, setHistoricalData] = useState<any[]>([]);
  const [predictions, setPredictions] = useState<any[]>([]);
  const [currentPrices, setCurrentPrices] = useState<any[]>([]);

  const [volatility, setVolatility] = useState<Volatility | null>(null);
  const [trend, setTrend] = useState<Trend | null>(null);
  const [marketHealth, setMarketHealth] = useState<MarketHealth | null>(null);
  const [insights, setInsights] = useState<string[]>([]);
  const [marketComparison, setMarketComparison] = useState<any[]>([]);
  const [seasonal, setSeasonal] = useState<any>(null);

  const [loading, setLoading] = useState(false);

  // Fetch initial data
  useEffect(() => {
    fetchCommodities();
    fetchStates();
  }, []);

  // Fetch data when selection changes
  useEffect(() => {
    if (selectedCommodity && selectedState) {
      fetchAllData();
    }
  }, [selectedCommodity, selectedState]);

  const fetchCommodities = async () => {
    try {
      const response = await axios.get(`${API_BASE}/commodities`);
      setCommodities(response.data.commodities);
      if (response.data.commodities.length > 0) {
        setSelectedCommodity(response.data.commodities[0]);
      }
    } catch (error) {
      console.error('Error fetching commodities:', error);
    }
  };

  const fetchStates = async () => {
    try {
      const response = await axios.get(`${API_BASE}/states`);
      setStates(response.data.states);
      if (response.data.states.length > 0) {
        setSelectedState(response.data.states[0]);
      }
    } catch (error) {
      console.error('Error fetching states:', error);
    }
  };

  const fetchAllData = async () => {
    setLoading(true);
    try {
      await Promise.all([
        fetchHistoricalData(),
        fetchPredictions(),
        fetchCurrentPrices(),
        fetchAnalytics(),
        fetchInsights()
      ]);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchHistoricalData = async () => {
    try {
      const response = await axios.get(
        `${API_BASE}/prices/history/${selectedCommodity}?state=${selectedState}&days=90`
      );
      setHistoricalData(response.data.history);
    } catch (error) {
      console.error('Error fetching historical data:', error);
    }
  };

  const fetchPredictions = async () => {
    try {
      const response = await axios.get(
        `${API_BASE}/predict/${selectedCommodity}/${selectedState}?days=7`
      );
      setPredictions(response.data.predictions || []);
    } catch (error) {
      console.error('Error fetching predictions:', error);
      setPredictions([]);
    }
  };

  const fetchCurrentPrices = async () => {
    try {
      const response = await axios.get(
        `${API_BASE}/prices/${selectedCommodity}/${selectedState}?limit=10`
      );
      setCurrentPrices(response.data.prices || []);
    } catch (error) {
      console.error('Error fetching current prices:', error);
    }
  };

  const fetchAnalytics = async () => {
    try {
      const [volRes, trendRes, compRes, seasonalRes] = await Promise.all([
        axios.get(`${API_BASE}/analytics/volatility/${selectedCommodity}/${selectedState}`),
        axios.get(`${API_BASE}/analytics/trends/${selectedCommodity}/${selectedState}`),
        axios.get(`${API_BASE}/analytics/market-comparison/${selectedCommodity}/${selectedState}?top_n=5`),
        axios.get(`${API_BASE}/analytics/seasonal/${selectedCommodity}?state=${selectedState}`)
      ]);

      setVolatility(volRes.data);
      setTrend(trendRes.data);
      setMarketComparison(compRes.data.markets || []);
      setSeasonal(seasonalRes.data);
    } catch (error) {
      console.error('Error fetching analytics:', error);
    }
  };

  const fetchInsights = async () => {
    try {
      const response = await axios.get(
        `${API_BASE}/analytics/insights/${selectedCommodity}/${selectedState}`
      );
      setInsights(response.data.insights || []);
      setMarketHealth(response.data.market_health);
    } catch (error) {
      console.error('Error fetching insights:', error);
    }
  };

  const handleTrainModel = async () => {
    setLoading(true);
    try {
      await axios.post(`${API_BASE}/train`, {
        commodity: selectedCommodity,
        state: selectedState
      });
      alert('Model trained successfully!');
      await fetchPredictions();
    } catch (error: any) {
      alert(`Training failed: ${error.response?.data?.detail || 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const getHealthColor = (score: number) => {
    if (score >= 80) return '#10b981';
    if (score >= 60) return '#3b82f6';
    if (score >= 40) return '#f59e0b';
    return '#ef4444';
  };

  const getVolatilityColor = (classification: string) => {
    const colors: any = {
      'LOW': '#10b981',
      'MODERATE': '#3b82f6',
      'HIGH': '#f59e0b',
      'VERY_HIGH': '#ef4444'
    };
    return colors[classification] || '#6b7280';
  };

  const getTrendColor = (trend: string) => {
    if (trend === 'UPWARD') return '#10b981';
    if (trend === 'DOWNWARD') return '#ef4444';
    return '#6b7280';
  };

  // Combine historical and prediction data for chart
  const chartData = [
    ...historicalData.map(d => ({ date: d.date, price: d.price, type: 'historical' })),
    ...predictions.map(p => ({
      date: p.date,
      price: p.predicted_price,
      priceLow: p.price_low,
      priceHigh: p.price_high,
      type: 'prediction'
    }))
  ];

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <h1>🌾 MSP Mitra - Price Intelligence</h1>
          <p>Advanced Agricultural Market Analytics & AI Predictions</p>
        </div>
      </header>

      {/* Controls */}
      <div className="controls">
        <div className="control-group">
          <label>Commodity</label>
          <select
            value={selectedCommodity}
            onChange={(e) => setSelectedCommodity(e.target.value)}
            disabled={loading}
          >
            {commodities.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>State</label>
          <select
            value={selectedState}
            onChange={(e) => setSelectedState(e.target.value)}
            disabled={loading}
          >
            {states.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <button onClick={fetchAllData} disabled={loading} className="btn-refresh">
          {loading ? '🔄 Loading...' : '🔄 Refresh Data'}
        </button>

        <button onClick={handleTrainModel} disabled={loading} className="btn-train">
          🧠 Train Model
        </button>
      </div>

      {loading && <div className="loading-overlay">Loading analytics...</div>}

      {/* Market Health & Stats Dashboard */}
      <div className="stats-grid">
        {/* Market Health */}
        {marketHealth && (
          <div className="stat-card health-card">
            <div className="stat-header">
              <span className="stat-icon">💚</span>
              <span className="stat-label">Market Health</span>
            </div>
            <div className="health-score" style={{ color: getHealthColor(marketHealth.score) }}>
              {marketHealth.score}/100
            </div>
            <div className="health-status">{marketHealth.status}</div>
            <div className="health-bar">
              <div
                className="health-bar-fill"
                style={{
                  width: `${marketHealth.score}%`,
                  backgroundColor: getHealthColor(marketHealth.score)
                }}
              />
            </div>
          </div>
        )}

        {/* Volatility */}
        {volatility && (
          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-icon">📊</span>
              <span className="stat-label">Price Volatility</span>
            </div>
            <div className="stat-value" style={{ color: getVolatilityColor(volatility.classification) }}>
              {volatility.volatility_score.toFixed(1)}%
            </div>
            <div className="stat-detail">{volatility.classification}</div>
            <div className="stat-subtext">Avg: ₹{volatility.mean_price.toFixed(2)}/qt</div>
          </div>
        )}

        {/* Trend */}
        {trend && (
          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-icon">📈</span>
              <span className="stat-label">Price Trend</span>
            </div>
            <div className="stat-value" style={{ color: getTrendColor(trend.trend) }}>
              {trend.indicator} {trend.change_percent > 0 ? '+' : ''}{trend.change_percent.toFixed(1)}%
            </div>
            <div className="stat-detail">{trend.trend} - {trend.strength_label}</div>
          </div>
        )}

        {/* Average Price */}
        {currentPrices.length > 0 && (
          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-icon">💰</span>
              <span className="stat-label">Current Avg Price</span>
            </div>
            <div className="stat-value">
              ₹{(currentPrices.reduce((sum, p) => sum + p.modal_price, 0) / currentPrices.length).toFixed(2)}
            </div>
            <div className="stat-detail">per Quintal</div>
            <div className="stat-subtext">{currentPrices.length} markets</div>
          </div>
        )}
      </div>

      {/* AI Insights Panel */}
      {insights.length > 0 && (
        <div className="insights-panel">
          <h2>🤖 AI Market Insights</h2>
          <div className="insights-list">
            {insights.map((insight, idx) => (
              <div key={idx} className="insight-item">
                <span className="insight-bullet">•</span>
                <span className="insight-text">{insight}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Advanced Price Chart */}
      <div className="chart-container">
        <h2>📈 Price Analysis & Predictions</h2>
        <ResponsiveContainer width="100%" height={400}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.1} />
              </linearGradient>
              <linearGradient id="colorPrediction" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="date" stroke="#9ca3af" />
            <YAxis stroke="#9ca3af" />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
              labelStyle={{ color: '#f3f4f6' }}
            />
            <Legend />
            <Area
              type="monotone"
              dataKey="price"
              stroke="#3b82f6"
              fillOpacity={1}
              fill="url(#colorPrice)"
              name="Historical Price"
            />
            <Area
              type="monotone"
              dataKey="priceLow"
              stroke="#6b7280"
              strokeDasharray="5 5"
              fill="none"
              name="Confidence Low"
            />
            <Area
              type="monotone"
              dataKey="priceHigh"
              stroke="#6b7280"
              strokeDasharray="5 5"
              fill="none"
              name="Confidence High"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Market Comparison Table */}
      {marketComparison.length > 0 && (
        <div className="table-container">
          <h2>🏪 Market Price Comparison</h2>
          <table className="price-table">
            <thead>
              <tr>
                <th>Market</th>
                <th>District</th>
                <th>Modal Price</th>
                <th>Min-Max Range</th>
                <th>vs Avg</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {marketComparison.map((market, idx) => (
                <tr key={idx}>
                  <td className="market-name">{market.market}</td>
                  <td>{market.district}</td>
                  <td className="price-value">₹{market.modal_price}</td>
                  <td className="price-range">₹{market.min_price} - ₹{market.max_price}</td>
                  <td className={market.diff_from_avg_percent > 0 ? 'positive' : 'negative'}>
                    {market.diff_from_avg_percent > 0 ? '+' : ''}{market.diff_from_avg_percent}%
                  </td>
                  <td>
                    <span className={`status-badge ${market.price_status.toLowerCase()}`}>
                      {market.price_status.replace('_', ' ')}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Seasonal Pattern */}
      {seasonal && seasonal.has_pattern && (
        <div className="seasonal-container">
          <h2>🌱 Seasonal Price Pattern</h2>
          <div className="seasonal-summary">
            <div className="seasonal-item peak">
              <div className="seasonal-label">Peak Month</div>
              <div className="seasonal-value">{seasonal.peak_month}</div>
              <div className="seasonal-price">₹{seasonal.peak_price}</div>
            </div>
            <div className="seasonal-item trough">
              <div className="seasonal-label">Lowest Month</div>
              <div className="seasonal-value">{seasonal.trough_month}</div>
              <div className="seasonal-price">₹{seasonal.trough_price}</div>
            </div>
            <div className="seasonal-item strength">
              <div className="seasonal-label">Seasonal Strength</div>
              <div className="seasonal-value">{seasonal.seasonal_strength_label}</div>
              <div className="seasonal-price">{seasonal.seasonal_strength}%</div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="footer">
        <p>MSP Mitra v2.0 - Powered by Multi-Model AI | Data: 1.1M+ Records |
          {selectedCommodity} in {selectedState}</p>
      </footer>
    </div>
  );
}

export default App;
