'use client';

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import ProteinEngineering from '@/components/ProteinEngineering';
import RecommendationPanel from '@/components/RecommendationPanel';

interface TraitConfig {
  crop: string;
  region: string;
  season: string;
  drought_tolerance: number;
  heat_resistance: number;
  disease_resistance: number;
  salinity_resistance: number;
  photosynthesis_efficiency: number;
  nitrogen_efficiency: number;
  [key: string]: string | number;
}

interface RecommendedProtein {
  trait: string;
  intensity: number;
  proteins: string[];
  pdb_ids: string[];
  genes: string[];
  mechanism: string;
  yield_contribution: number;
}

interface ProteinResult {
  crop: string;
  region: string;
  baseline_yield: number;
  projected_yield: number;
  yield_increase_percent: number;
  selected_traits: Record<string, number>;
  recommended_proteins: RecommendedProtein[];
  climate_resilience_score: number;
  feasibility_score: number;
  recommendations: string[];
}

const ProteinVisualization = dynamic(
  () => import('@/components/ProteinVisualization'),
  { 
    ssr: false,
    loading: () => (
      <div className="viz-loading-container">
        <div className="viz-loading-spinner"></div>
        <p className="viz-loading-text">Loading 3D Viewer...</p>
      </div>
    )
  }
);

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function ProteinEngineeringPage() {
  const [isClient, setIsClient] = useState(false);
  const [config, setConfig] = useState<TraitConfig>({
    crop: 'Wheat',
    region: 'Punjab',
    season: 'Rabi',
    drought_tolerance: 0,
    heat_resistance: 0,
    disease_resistance: 0,
    salinity_resistance: 0,
    photosynthesis_efficiency: 0,
    nitrogen_efficiency: 0,
  });

  const [result, setResult] = useState<ProteinResult | null>(null);
  const [selectedProtein, setSelectedProtein] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'visualization' | 'recommendations'>('visualization');

  useEffect(() => {
    setIsClient(true);
  }, []);

  const handleTraitChange = (trait: string, value: number) => {
    setConfig(prev => ({ ...prev, [trait]: value }));
  };

  const handleCropChange = (crop: string) => {
    setConfig(prev => ({ ...prev, crop }));
  };

  const handleRegionChange = (region: string) => {
    setConfig(prev => ({ ...prev, region }));
  };

  const handleSeasonChange = (season: string) => {
    setConfig(prev => ({ ...prev, season }));
  };

  const handleEngineer = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/engineer-trait`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config),
      });

      if (!response.ok) {
        throw new Error('Failed to engineer proteins');
      }

      const data = await response.json();
      setResult(data);

      if (data.recommended_proteins?.[0]?.pdb_ids?.[0]) {
        setSelectedProtein(data.recommended_proteins[0].pdb_ids[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setConfig({
      crop: 'Wheat',
      region: 'Punjab',
      season: 'Rabi',
      drought_tolerance: 0,
      heat_resistance: 0,
      disease_resistance: 0,
      salinity_resistance: 0,
      photosynthesis_efficiency: 0,
      nitrogen_efficiency: 0,
    });
    setResult(null);
    setSelectedProtein(null);
    setError(null);
  };

  if (!isClient) {
    return (
      <div className="app-loading-state">
        <div className="app-loading-spinner"></div>
        <p>Loading Application...</p>
      </div>
    );
  }

  return (
    <div className="protein-engineering-app">
      <header className="app-hero">
        <div className="hero-bg-pattern"></div>
        <div className="hero-content-wrapper">
          <div className="hero-badge">
            <span className="badge-icon">🧬</span>
            <span className="badge-text">AI-Powered Protein Engineering</span>
          </div>
          <h1 className="hero-title">
            Molecular Crop Optimization Platform
          </h1>
          <p className="hero-description">
            Design enhanced crop traits through advanced protein engineering and 3D molecular visualization
          </p>
        </div>
      </header>

      <main className="app-main">
        <div className="content-layout">
          <aside className="config-panel">
            <div className="panel-wrapper">
              <div className="panel-header-section">
                <div className="panel-icon-wrapper">
                  <span className="panel-icon">⚙️</span>
                </div>
                <div className="panel-header-text">
                  <h2 className="panel-heading">Trait Configuration</h2>
                  <p className="panel-subheading">Optimize crop characteristics</p>
                </div>
              </div>

              <ProteinEngineering
                config={config}
                onTraitChange={handleTraitChange}
                onCropChange={handleCropChange}
                onRegionChange={handleRegionChange}
                onSeasonChange={handleSeasonChange}
                onEngineer={handleEngineer}
                onReset={handleReset}
                loading={loading}
              />
            </div>

            {error && (
              <div className="error-alert">
                <div className="alert-icon-wrapper">
                  <span className="alert-icon">⚠️</span>
                </div>
                <div className="alert-content">
                  <h4 className="alert-title">Connection Error</h4>
                  <p className="alert-message">{error}</p>
                </div>
              </div>
            )}
          </aside>

          <section className="results-panel">
            {result ? (
              <>
                <div className="stats-container">
                  <div className="stat-box stat-primary">
                    <div className="stat-icon-bg">
                      <span className="stat-emoji">📈</span>
                    </div>
                    <div className="stat-details">
                      <p className="stat-label">Yield Increase</p>
                      <p className="stat-value">{result.yield_increase_percent.toFixed(1)}%</p>
                      <p className="stat-sublabel">Estimated improvement</p>
                    </div>
                  </div>

                  <div className="stat-box stat-success">
                    <div className="stat-icon-bg">
                      <span className="stat-emoji">🌾</span>
                    </div>
                    <div className="stat-details">
                      <p className="stat-label">Projected Yield</p>
                      <p className="stat-value">{result.projected_yield.toFixed(0)}</p>
                      <p className="stat-sublabel">kg/hectare</p>
                    </div>
                  </div>

                  <div className="stat-box stat-info">
                    <div className="stat-icon-bg">
                      <span className="stat-emoji">🛡️</span>
                    </div>
                    <div className="stat-details">
                      <p className="stat-label">Resilience</p>
                      <p className="stat-value">{result.climate_resilience_score.toFixed(0)}</p>
                      <p className="stat-sublabel">Climate adaptation</p>
                    </div>
                  </div>

                  <div className="stat-box stat-warning">
                    <div className="stat-icon-bg">
                      <span className="stat-emoji">✅</span>
                    </div>
                    <div className="stat-details">
                      <p className="stat-label">Feasibility</p>
                      <p className="stat-value">{result.feasibility_score.toFixed(0)}%</p>
                      <p className="stat-sublabel">Implementation score</p>
                    </div>
                  </div>
                </div>

                <div className="tab-navigation">
                  <div className="tab-buttons-wrapper">
                    <button
                      onClick={() => setActiveTab('visualization')}
                      className={`tab-btn ${activeTab === 'visualization' ? 'tab-btn-active' : ''}`}
                    >
                      <span className="tab-icon">🧬</span>
                      <span className="tab-text">3D Visualization</span>
                    </button>
                    
                    <button
                      onClick={() => setActiveTab('recommendations')}
                      className={`tab-btn ${activeTab === 'recommendations' ? 'tab-btn-active' : ''}`}
                    >
                      <span className="tab-icon">📊</span>
                      <span className="tab-text">Recommendations</span>
                    </button>
                  </div>
                </div>

                <div className="tab-content-area">
                  {activeTab === 'visualization' ? (
                    <div className="visualization-container">
                      <div className="viz-header">
                        <h3 className="viz-title">Interactive 3D Protein Structure</h3>
                        <p className="viz-subtitle">
                          Click atoms to explore molecular properties
                        </p>
                      </div>
                      
                      <div className="viz-wrapper">
                        {selectedProtein && (
                          <ProteinVisualization
                            proteinId={selectedProtein}
                            selectedProtein={selectedProtein}
                          />
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="recommendations-container">
                      <RecommendationPanel result={result} />
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="empty-results-state">
                <div className="empty-icon-wrapper">
                  <span className="empty-icon">🧪</span>
                </div>
                <h3 className="empty-title">Ready to Optimize</h3>
                <p className="empty-description">
                  Configure crop traits and click <strong>"Engineer Traits"</strong> to begin
                </p>
                
                <div className="features-showcase">
                  <div className="feature-highlight">
                    <div className="feature-icon">⚛️</div>
                    <div className="feature-text">
                      <h4>Interactive 3D</h4>
                      <p>Clickable structures</p>
                    </div>
                  </div>

                  <div className="feature-highlight">
                    <div className="feature-icon">🔗</div>
                    <div className="feature-text">
                      <h4>Bond Analysis</h4>
                      <p>Real-time data</p>
                    </div>
                  </div>

                  <div className="feature-highlight">
                    <div className="feature-icon">🧬</div>
                    <div className="feature-text">
                      <h4>DNA Support</h4>
                      <p>Auto-detection</p>
                    </div>
                  </div>

                  <div className="feature-highlight">
                    <div className="feature-icon">📊</div>
                    <div className="feature-text">
                      <h4>Statistics</h4>
                      <p>Comprehensive analysis</p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}