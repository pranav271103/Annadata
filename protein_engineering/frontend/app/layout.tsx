import type { Metadata } from 'next';
import Image from 'next/image';
import './globals.css';

export const metadata: Metadata = {
  title: 'Annadata – Agricultural Intelligence for India',
  description:
    'UX4G-inspired Indian agriculture platform for climate-smart crop and protein optimization.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="ux4g-body">
        {/* Top India / accessibility strip */}
        <div className="ux4g-top-strip">
          <div className="ux4g-top-strip-left">
            <span className="ux4g-top-strip-flag" aria-hidden="true" />
            <span className="ux4g-top-strip-text">
              Government of India inspired agri-intelligence experience
            </span>
          </div>
          <div className="ux4g-top-strip-right">
            <button className="ux4g-a11y-btn" type="button">
              A-
            </button>
            <button className="ux4g-a11y-btn" type="button">
              A
            </button>
            <button className="ux4g-a11y-btn" type="button">
              A+
            </button>
            <button className="ux4g-a11y-btn ux4g-a11y-contrast" type="button">
              ⬤
            </button>
          </div>
        </div>

        {/* Main shell */}
        <div className="ux4g-shell">
          <header className="ux4g-header">
            <div className="ux4g-header-inner">
              <div className="ux4g-brand">
                <div className="ux4g-logo-wrapper">
                  <Image
                    src="/annadata-logo.png"
                    alt="Annadata – Agricultural Intelligence"
                    fill
                    sizes="120px"
                    className="ux4g-logo-image"
                    priority
                  />
                </div>
                <div className="ux4g-brand-text">
                  <p className="ux4g-brand-title">Annadata</p>
                  <p className="ux4g-brand-subtitle">
                    Agricultural Intelligence for India
                  </p>
                </div>
              </div>

              <nav className="ux4g-nav" aria-label="Primary">
                <a href="#" className="ux4g-nav-link ux4g-nav-link-active">
                  Home
                </a>
                <a href="#" className="ux4g-nav-link">
                  Crop Insights
                </a>
                <a href="#" className="ux4g-nav-link">
                  Weather &amp; Climate
                </a>
                <a href="#" className="ux4g-nav-link">
                  Protein Engineering
                </a>
                <a href="#" className="ux4g-nav-link">
                  Resources
                </a>
              </nav>
            </div>
          </header>

          <main className="ux4g-main">{children}</main>

          <footer className="ux4g-footer">
            <div className="ux4g-footer-inner">
              <div className="ux4g-footer-left">
                <p className="ux4g-footer-title">Annadata Platform</p>
                <p className="ux4g-footer-text">
                  Built for Indian farmers, researchers, and policymakers to
                  accelerate climate-resilient agriculture.
                </p>
              </div>
              <div className="ux4g-footer-right">
                <div className="ux4g-footer-links">
                  <a href="#" className="ux4g-footer-link">
                    About
                  </a>
                  <a href="#" className="ux4g-footer-link">
                    Documentation
                  </a>
                  <a href="#" className="ux4g-footer-link">
                    Contact
                  </a>
                </div>
                <p className="ux4g-footer-meta">
                  UX4G-inspired interface • Made for Bharat&apos;s Annadata
                </p>
              </div>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
