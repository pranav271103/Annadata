'use client';

import React, { useState, useEffect } from 'react';
import HomeView from '@/components/HomeView';
import ProteinEngineeringView from '@/components/ProteinEngineeringView';
import ResourcesView from '@/components/ResourcesView';

export default function Page() {
  const [isClient, setIsClient] = useState(false);
  const [activeTab, setActiveTab] = useState<'home' | 'engineering' | 'resources'>('home');
  const [fontSize, setFontSize] = useState(100);

  useEffect(() => {
    setIsClient(true);
    document.documentElement.style.fontSize = `${fontSize}%`;
  }, [fontSize]);

  const handleSkipToContent = () => {
    const mainContent = document.getElementById('main-content');
    if (mainContent) {
      mainContent.scrollIntoView({ behavior: 'smooth' });
    } else {
      // If not on home tab, switch to home and then scroll
      setActiveTab('home');
      setTimeout(() => {
        const content = document.getElementById('main-content');
        content?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    }
  };

  const handleFontSizeChange = (action: 'increase' | 'decrease' | 'reset') => {
    if (action === 'increase') setFontSize(prev => Math.min(prev + 10, 150));
    if (action === 'decrease') setFontSize(prev => Math.max(prev - 10, 80));
    if (action === 'reset') setFontSize(100);
  };

  if (!isClient) {
    return (
      <div className="app-loading-state">
        <div className="app-loading-spinner"></div>
        <p>Loading Annadata...</p>
      </div>
    );
  }

  return (
    <div className="protein-engineering-app ux4g-body">
      {/* UX4G Top Strip */}
      <div className="ux4g-top-strip">
        <div className="ux4g-top-strip-left">
          <div className="ux4g-top-strip-flag" role="img" aria-label="Indian Flag"></div>
          <span className="ux4g-top-strip-text">Government of India Inspired UI</span>
        </div>
        <div className="ux4g-top-strip-right">
          <button onClick={handleSkipToContent} className="ux4g-a11y-btn">Skip to Main Content</button>
          <div className="ux4g-a11y-controls" style={{ display: 'flex', gap: '0.25rem' }}>
            <button onClick={() => handleFontSizeChange('decrease')} className="ux4g-a11y-btn" title="Decrease Font Size">A-</button>
            <button onClick={() => handleFontSizeChange('reset')} className="ux4g-a11y-btn" title="Reset Font Size">A</button>
            <button onClick={() => handleFontSizeChange('increase')} className="ux4g-a11y-btn" title="Increase Font Size">A+</button>
          </div>
        </div>
      </div>

      {/* UX4G Header */}
      <header>
        <div className="ux4g-header">
          <div className="ux4g-header-inner">
            <div className="ux4g-brand">
              <div className="ux4g-logo-wrapper">
                {/* Use a placeholder or the actual logo if available */}
                <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem' }}>🌾</div>
              </div>
              <div className="ux4g-brand-text">
                <h1 className="ux4g-brand-title">Annadata</h1>
                <span className="ux4g-brand-subtitle">Kisan Ki Unnati</span>
              </div>
            </div>

            <nav className="ux4g-nav">
              <button
                onClick={() => setActiveTab('home')}
                className={`ux4g-nav-link ${activeTab === 'home' ? 'ux4g-nav-link-active' : ''}`}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem' }}
              >
                Home
              </button>
              <button
                onClick={() => setActiveTab('engineering')}
                className={`ux4g-nav-link ${activeTab === 'engineering' ? 'ux4g-nav-link-active' : ''}`}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem' }}
              >
                Protein Engineering
              </button>
              <button
                onClick={() => setActiveTab('resources')}
                className={`ux4g-nav-link ${activeTab === 'resources' ? 'ux4g-nav-link-active' : ''}`}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem' }}
              >
                Resources
              </button>
            </nav>
          </div>
        </div>
      </header>

      <main className="ux4g-main">
        {activeTab === 'home' && <HomeView />}
        {activeTab === 'engineering' && (
          <div className="ux4g-shell">
            <ProteinEngineeringView />
          </div>
        )}
        {activeTab === 'resources' && <ResourcesView />}
      </main>

      <footer className="ux4g-shell">
        <div className="ux4g-footer">
          <div className="ux4g-footer-inner">
            <div>
              <h4 className="ux4g-footer-title">Annadata Platform</h4>
              <p className="ux4g-footer-text">
                Empowering Indian farmers with climate-resilient crop traits designed through advanced protein engineering and AI.
              </p>
            </div>
            <div className="ux4g-footer-right">
              <div className="ux4g-footer-links">
                <a
                  href="https://github.com/pranav271103/Annadata"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ux4g-footer-link"
                >
                  Github
                </a>
                <a href="mailto:raman@rmnm.in" className="ux4g-footer-link">Contact Us</a>
              </div>
              <div className="ux4g-footer-meta">
                © {new Date().getFullYear()} Annadata. All rights reserved.
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}