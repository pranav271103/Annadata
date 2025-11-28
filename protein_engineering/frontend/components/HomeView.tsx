import React from 'react';

export default function HomeView() {
    return (
        <div className="home-view">
            <header className="app-hero home-hero">
                <div className="hero-bg-pattern"></div>
                <div className="hero-content-wrapper">
                    <div className="hero-badge">
                        <span className="badge-icon">🧬</span>
                        <span className="badge-text">India-first Climate & Protein Intelligence</span>
                    </div>
                    <h1 className="hero-title">
                        Agricultural Intelligence for India&apos;s Annadata
                    </h1>
                    <p className="hero-description">
                        Design climate-smart crop traits for Indian states and seasons with advanced protein engineering,
                        pan-India datasets, and interactive 3D molecular visualization.
                    </p>
                </div>
            </header>

            <section className="intro-section" id="main-content">
                <div className="ux4g-shell">
                    <div className="intro-content">
                        <h2 className="section-title">Empowering Indian Agriculture</h2>
                        <p className="section-text">
                            Annadata leverages cutting-edge protein engineering and AI to address the unique challenges faced by Indian farmers.
                            By analyzing vast datasets of crop traits across different states and seasons, we enable the design of crops that are resilient to climate change, pests, and diseases.
                        </p>

                        <div className="features-grid">
                            <div className="feature-card">
                                <div className="feature-icon-lg">🌾</div>
                                <h3>Climate-Smart Traits</h3>
                                <p>Tailored recommendations for drought, heat, and salinity resistance specific to Indian regions.</p>
                            </div>
                            <div className="feature-card">
                                <div className="feature-icon-lg">🧬</div>
                                <h3>Protein Engineering</h3>
                                <p>Advanced molecular modeling to visualize and optimize protein structures for better yield.</p>
                            </div>
                            <div className="feature-card">
                                <div className="feature-icon-lg">🇮🇳</div>
                                <h3>Pan-India Data</h3>
                                <p>Insights derived from decades of agricultural data across all major Indian states.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
        </div>
    );
}
