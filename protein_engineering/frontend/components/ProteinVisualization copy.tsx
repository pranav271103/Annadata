'use client';

import React, { useEffect, useRef, useState } from 'react';

interface ProteinVisualizationProps {
  proteinId: string;
  selectedProtein: string;
}

type AtomInfo = {
  element?: string;
  atom?: string;
  residueName?: string;
  residueIndex?: number;
  chain?: string;
  x?: number;
  y?: number;
  z?: number;
  serial?: number;
};

export default function ProteinVisualization({
  proteinId,
}: ProteinVisualizationProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scriptLoaded, setScriptLoaded] = useState(false);
  const [atomInfo, setAtomInfo] = useState<AtomInfo | null>(null);

  // Load 3Dmol.js script once
  useEffect(() => {
    if (typeof window !== 'undefined' && !(window as any).$3Dmol) {
      const script = document.createElement('script');
      script.src = 'https://3Dmol.csb.pitt.edu/build/3Dmol-min.js';
      script.async = true;
      script.onload = () => setScriptLoaded(true);
      script.onerror = () => setError('Failed to load 3Dmol.js library');
      document.head.appendChild(script);
    } else if ((window as any).$3Dmol) {
      setScriptLoaded(true);
    }
  }, []);

  // Load protein once script is ready
  useEffect(() => {
    if (!scriptLoaded) return;

    const mountTimer = setTimeout(() => {
      if (!containerRef.current) {
        setError('Container mount failed');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      setAtomInfo(null);

      const $3Dmol = (window as any).$3Dmol;

      if (!$3Dmol) {
        setError('3Dmol library not available');
        setLoading(false);
        return;
      }

      try {
        // Clear container
        containerRef.current.innerHTML = '';

        // Create viewer
        const config = { backgroundColor: 'white' };
        const viewer = $3Dmol.createViewer(containerRef.current, config);
        viewerRef.current = viewer;

        // PDB URL
        const pdbUrl = `https://files.rcsb.org/download/${proteinId}.pdb`;

        // Load PDB with timeout
        const timeoutId = setTimeout(() => {
          setError('Loading timeout - server not responding');
          setLoading(false);
        }, 15000);

        // Fetch and load structure
        fetch(pdbUrl)
          .then((response) => {
            clearTimeout(timeoutId);
            if (!response.ok) {
              throw new Error(`PDB fetch failed: ${response.status}`);
            }
            return response.text();
          })
          .then((pdbData) => {
            // Add model
            viewer.addModel(pdbData, 'pdb');

            // Base style - cartoon representation
            viewer.setStyle({}, { cartoon: { color: 'spectrum' } });

            // Add stick representation for better visibility
            viewer.addStyle({}, {
              stick: {
                radius: 0.15,
                colorscheme: 'Jmol',
              },
            });

            // Enable atom clicking
            viewer.setClickable(
              {},
              true,
              (atom: any) => {
                if (!atom) return;

                // Clear previous highlighting
                viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
                viewer.addStyle({}, {
                  stick: {
                    radius: 0.15,
                    colorscheme: 'Jmol',
                  },
                });

                // Highlight clicked atom in yellow
                viewer.addStyle(
                  { serial: atom.serial },
                  {
                    sphere: {
                      radius: 0.5,
                      color: 'yellow',
                    },
                  }
                );

                viewer.render();

                // Update atom info state
                setAtomInfo({
                  element: atom.elem,
                  atom: atom.atom,
                  residueName: atom.resn,
                  residueIndex: atom.resi,
                  chain: atom.chain,
                  x: atom.x,
                  y: atom.y,
                  z: atom.z,
                  serial: atom.serial,
                });
              },
              'Click to inspect atom'
            );

            // Center and zoom
            viewer.zoomTo();
            viewer.render();
            setLoading(false);
          })
          .catch((err) => {
            clearTimeout(timeoutId);
            console.error('Error loading protein:', err);

            let errorMsg = 'Failed to load protein structure';
            if (err.message.includes('404')) {
              errorMsg = `PDB ID "${proteinId}" not found`;
            } else if (
              err.message.includes('fetch') ||
              err.message.includes('network')
            ) {
              errorMsg = 'Network error - Check connection';
            }

            setError(errorMsg);
            setLoading(false);
          });
      } catch (err) {
        console.error('Viewer creation error:', err);
        setError('Failed to create viewer');
        setLoading(false);
      }
    }, 100);

    return () => clearTimeout(mountTimer);
  }, [scriptLoaded, proteinId]);

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '600px',
          gap: '1.5rem',
          background: 'linear-gradient(135deg, #f9fafb 0%, #ffffff 100%)',
          borderRadius: '0.75rem',
          border: '2px solid #e5e7eb',
          padding: '2rem',
        }}
      >
        <div
          style={{
            fontSize: '4rem',
            animation: 'spin 2s linear infinite',
          }}
        >
          🧬
        </div>

        <div style={{ textAlign: 'center' }}>
          <p
            style={{
              color: '#111827',
              fontWeight: 700,
              margin: '0 0 0.5rem 0',
              fontSize: '1.25rem',
            }}
          >
            Loading {proteinId}
          </p>
          <p
            style={{
              color: '#6b7280',
              fontSize: '0.875rem',
              margin: 0,
            }}
          >
            Loading 3D structure...
          </p>
        </div>

        <style jsx>{`
          @keyframes spin {
            to {
              transform: rotate(360deg);
            }
          }
        `}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: '1.5rem',
          background: 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)',
          borderRadius: '0.75rem',
          border: '2px solid #fca5a5',
        }}
      >
        <p
          style={{
            color: '#dc2626',
            fontWeight: 700,
            margin: '0 0 0.5rem 0',
          }}
        >
          ⚠️ {error}
        </p>
        <p style={{ color: '#991b1b', fontSize: '0.875rem' }}>
          Check internet connection or verify PDB ID on rcsb.org
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Success banner */}
      <div
        style={{
          marginBottom: '1rem',
          padding: '0.75rem 1rem',
          background: 'linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%)',
          borderRadius: '0.5rem',
          border: '1px solid #6ee7b7',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '1.5rem' }}>✅</span>
          <div>
            <p
              style={{
                fontSize: '0.9rem',
                fontWeight: 700,
                color: '#065f46',
                margin: 0,
              }}
            >
              Successfully loaded {proteinId}!
            </p>
            <p
              style={{
                fontSize: '0.75rem',
                color: '#047857',
                margin: 0,
              }}
            >
              Click any atom to inspect its details below.
            </p>
          </div>
        </div>
      </div>

      {/* 3D viewer */}
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: '500px',
          borderRadius: '0.75rem',
          overflow: 'hidden',
          border: '2px solid #e5e7eb',
          boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
          background: 'white',
        }}
      />

      {/* Atom details panel - only shows when atom is clicked */}
      {atomInfo && (
        <div
          style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
            borderRadius: '0.75rem',
            border: '2px solid #fbbf24',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '0.75rem',
            }}
          >
            <p
              style={{
                fontSize: '0.9rem',
                fontWeight: 700,
                color: '#92400e',
                margin: 0,
              }}
            >
              🧩 Selected Atom Details
            </p>
            <button
              onClick={() => setAtomInfo(null)}
              style={{
                padding: '0.25rem 0.75rem',
                background: '#f59e0b',
                color: 'white',
                border: 'none',
                borderRadius: '0.375rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              ✕ Close
            </button>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: '0.75rem',
            }}
          >
            <div
              style={{
                padding: '0.75rem',
                background: 'white',
                borderRadius: '0.5rem',
                border: '1px solid #fbbf24',
              }}
            >
              <div
                style={{
                  fontSize: '0.7rem',
                  color: '#92400e',
                  fontWeight: 600,
                  marginBottom: '0.25rem',
                }}
              >
                Element
              </div>
              <div
                style={{
                  fontSize: '1.25rem',
                  fontWeight: 700,
                  color: '#78350f',
                }}
              >
                {atomInfo.element || '-'}
              </div>
            </div>

            <div
              style={{
                padding: '0.75rem',
                background: 'white',
                borderRadius: '0.5rem',
                border: '1px solid #fbbf24',
              }}
            >
              <div
                style={{
                  fontSize: '0.7rem',
                  color: '#92400e',
                  fontWeight: 600,
                  marginBottom: '0.25rem',
                }}
              >
                Atom Name
              </div>
              <div
                style={{
                  fontSize: '1.25rem',
                  fontWeight: 700,
                  color: '#78350f',
                }}
              >
                {atomInfo.atom || '-'}
              </div>
            </div>

            <div
              style={{
                padding: '0.75rem',
                background: 'white',
                borderRadius: '0.5rem',
                border: '1px solid #fbbf24',
              }}
            >
              <div
                style={{
                  fontSize: '0.7rem',
                  color: '#92400e',
                  fontWeight: 600,
                  marginBottom: '0.25rem',
                }}
              >
                Residue
              </div>
              <div
                style={{
                  fontSize: '1rem',
                  fontWeight: 700,
                  color: '#78350f',
                }}
              >
                {atomInfo.residueName
                  ? `${atomInfo.residueName} ${atomInfo.residueIndex}`
                  : '-'}
              </div>
            </div>

            <div
              style={{
                padding: '0.75rem',
                background: 'white',
                borderRadius: '0.5rem',
                border: '1px solid #fbbf24',
              }}
            >
              <div
                style={{
                  fontSize: '0.7rem',
                  color: '#92400e',
                  fontWeight: 600,
                  marginBottom: '0.25rem',
                }}
              >
                Chain
              </div>
              <div
                style={{
                  fontSize: '1.25rem',
                  fontWeight: 700,
                  color: '#78350f',
                }}
              >
                {atomInfo.chain || '-'}
              </div>
            </div>

            <div
              style={{
                padding: '0.75rem',
                background: 'white',
                borderRadius: '0.5rem',
                border: '1px solid #fbbf24',
              }}
            >
              <div
                style={{
                  fontSize: '0.7rem',
                  color: '#92400e',
                  fontWeight: 600,
                  marginBottom: '0.25rem',
                }}
              >
                Serial #
              </div>
              <div
                style={{
                  fontSize: '1rem',
                  fontWeight: 700,
                  color: '#78350f',
                }}
              >
                {atomInfo.serial ?? '-'}
              </div>
            </div>

            <div
              style={{
                padding: '0.75rem',
                background: 'white',
                borderRadius: '0.5rem',
                border: '1px solid #fbbf24',
                gridColumn: 'span 2',
              }}
            >
              <div
                style={{
                  fontSize: '0.7rem',
                  color: '#92400e',
                  fontWeight: 600,
                  marginBottom: '0.25rem',
                }}
              >
                3D Coordinates (Å)
              </div>
              <div
                style={{
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  color: '#78350f',
                  fontFamily: 'monospace',
                }}
              >
                X: {atomInfo.x !== undefined ? atomInfo.x.toFixed(2) : '-'} | Y:{' '}
                {atomInfo.y !== undefined ? atomInfo.y.toFixed(2) : '-'} | Z:{' '}
                {atomInfo.z !== undefined ? atomInfo.z.toFixed(2) : '-'}
              </div>
            </div>
          </div>

          <div
            style={{
              marginTop: '0.75rem',
              padding: '0.75rem',
              background: 'rgba(245, 158, 11, 0.2)',
              borderRadius: '0.5rem',
              fontSize: '0.75rem',
              color: '#78350f',
            }}
          >
            💡 <strong>Tip:</strong> Click another atom to update these details, or close this
            panel to continue exploring.
          </div>
        </div>
      )}

      {/* Controls info */}
      <div
        style={{
          marginTop: '1rem',
          padding: '1rem',
          background: 'linear-gradient(135deg, #f9fafb 0%, #ffffff 100%)',
          borderRadius: '0.5rem',
          border: '1px solid #e5e7eb',
        }}
      >
        <p
          style={{
            fontSize: '0.75rem',
            color: '#111827',
            fontWeight: 600,
            margin: '0 0 0.5rem 0',
          }}
        >
          🎮 Controls:
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '0.5rem',
            fontSize: '0.75rem',
            color: '#6b7280',
          }}
        >
          <div>
            🖱️ <strong>Left Click + Drag:</strong> Rotate
          </div>
          <div>
            🖱️ <strong>Right Click + Drag:</strong> Move
          </div>
          <div>
            🖱️ <strong>Scroll:</strong> Zoom in/out
          </div>
          <div>
            ⚛️ <strong>Click Atom:</strong> Show details
          </div>
        </div>
      </div>
    </div>
  );
}