'use client';

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';

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
  const [mounted, setMounted] = useState(false);

  // Mark as mounted on client-side
  useLayoutEffect(() => {
    console.log('✅ [Component] Client-side mounted');
    setMounted(true);
  }, []);

  // Load 3Dmol.js script once
  useEffect(() => {
    if (!mounted) return;

    console.log('🔧 [3Dmol] Initializing 3Dmol.js...');
    
    if (typeof window !== 'undefined' && !(window as any).$3Dmol) {
      console.log('📦 [3Dmol] Loading library from CDN...');
      const script = document.createElement('script');
      script.src = 'https://3Dmol.csb.pitt.edu/build/3Dmol-min.js';
      script.async = true;
      script.onload = () => {
        console.log('✅ [3Dmol] Library loaded successfully');
        setScriptLoaded(true);
      };
      script.onerror = () => {
        console.error('❌ [3Dmol] Failed to load library');
        setError('Failed to load 3Dmol.js library');
        setLoading(false);
      };
      document.head.appendChild(script);
    } else if ((window as any).$3Dmol) {
      console.log('✅ [3Dmol] Library already loaded in window');
      setScriptLoaded(true);
    }
  }, [mounted]);

  // Load protein once script is ready AND mounted
  useEffect(() => {
    if (!scriptLoaded || !mounted || !containerRef.current) {
      console.log(`⏳ [Loading] scriptLoaded=${scriptLoaded}, mounted=${mounted}, containerReady=${!!containerRef.current}`);
      return;
    }

    console.log(`🧬 [Protein] Starting load: ${proteinId}`);
    setLoading(true);
    setError(null);
    setAtomInfo(null);

    const $3Dmol = (window as any).$3Dmol;

    if (!$3Dmol) {
      console.error('❌ [3Dmol] Library not available in window');
      setError('3Dmol library not available');
      setLoading(false);
      return;
    }

    try {
      const container = containerRef.current;
      
      if (!container) {
        console.error('❌ [Container] Container is null');
        setError('Container not found');
        setLoading(false);
        return;
      }

      // Clear container
      container.innerHTML = '';
      console.log('🧹 [3Dmol] Container cleared');

      // Create viewer
      const config = { backgroundColor: 'white' };
      console.log('🎨 [3Dmol] Creating viewer...');
      const viewer = $3Dmol.createViewer(container, config);
      
      if (!viewer) {
        console.error('❌ [3Dmol] Failed to create viewer');
        setError('Failed to create viewer');
        setLoading(false);
        return;
      }

      viewerRef.current = viewer;
      console.log('✅ [3Dmol] Viewer created successfully');

      // PDB URL
      const pdbUrl = `https://files.rcsb.org/download/${proteinId}.pdb`;
      console.log(`🌐 [Protein] Fetching from: ${pdbUrl}`);

      // Load PDB with timeout
      const timeoutId = setTimeout(() => {
        console.error('⏱️ [Protein] Loading timeout (15s)');
        setError('Loading timeout - server not responding');
        setLoading(false);
      }, 15000);

      // Fetch and load structure
      fetch(pdbUrl)
        .then((response) => {
          clearTimeout(timeoutId);
          console.log(`📥 [Protein] Response: ${response.status} ${response.statusText}`);
          
          if (!response.ok) {
            throw new Error(`PDB fetch failed: ${response.status}`);
          }
          return response.text();
        })
        .then((pdbData) => {
          console.log(`📊 [Protein] Data received: ${pdbData.length} characters`);
          
          // Add model
          console.log('🏗️ [3Dmol] Adding model...');
          viewer.addModel(pdbData, 'pdb');
          console.log('✅ [3Dmol] Model added');

          // Base style
          console.log('🎨 [3Dmol] Applying cartoon style...');
          viewer.setStyle({}, { cartoon: { color: 'spectrum' } });

          // Stick representation
          console.log('🎨 [3Dmol] Adding stick representation...');
          viewer.addStyle({}, {
            stick: {
              radius: 0.15,
              colorscheme: 'Jmol',
            },
          });
          console.log('✅ [3Dmol] Styles applied');

          // Enable atom clicking
          console.log('🖱️ [3Dmol] Enabling atom clicking...');
          viewer.setClickable(
            {},
            true,
            (atom: any) => {
              if (!atom) return;

              console.log(`⚛️ [Atom] Element: ${atom.elem}, Atom: ${atom.atom}, Residue: ${atom.resn}${atom.resi}, Chain: ${atom.chain}`);
              console.log(`📍 [Position] X: ${atom.x?.toFixed(2)}, Y: ${atom.y?.toFixed(2)}, Z: ${atom.z?.toFixed(2)}`);
              console.log(`🔢 [Serial] ${atom.serial}`);

              // Clear previous highlighting
              viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
              viewer.addStyle({}, {
                stick: {
                  radius: 0.15,
                  colorscheme: 'Jmol',
                },
              });

              // Highlight clicked atom
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

              // Update atom info
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
          console.log('✅ [3Dmol] Atom clicking enabled');

          // Zoom and render
          console.log('🔍 [3Dmol] Zooming to fit...');
          viewer.zoomTo();
          console.log('🎬 [3Dmol] Rendering...');
          viewer.render();
          console.log(`🎉 [SUCCESS] Loaded ${proteinId}!`);
          setLoading(false);
        })
        .catch((err) => {
          clearTimeout(timeoutId);
          console.error('❌ [Protein] Error:', err.message);

          let errorMsg = 'Failed to load protein structure';
          if (err.message.includes('404')) {
            errorMsg = `PDB ID "${proteinId}" not found`;
            console.error(`❌ [Protein] PDB not found: ${proteinId}`);
          } else if (
            err.message.includes('fetch') ||
            err.message.includes('network')
          ) {
            errorMsg = 'Network error - Check connection';
            console.error('❌ [Network] Connection error');
          }

          setError(errorMsg);
          setLoading(false);
        });
    } catch (err: any) {
      console.error('❌ [Exception] Error:', err?.message || err);
      setError('Failed to initialize viewer');
      setLoading(false);
    }
  }, [scriptLoaded, proteinId, mounted]);

  return (
    <div>
      {/* Container ALWAYS exists for ref - visibility controlled by CSS */}
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
          marginBottom: '1rem',
          visibility: loading || error ? 'hidden' : 'visible',
          position: loading || error ? 'absolute' : 'relative',
        }}
      />

      {/* Loading state */}
      {loading && (
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
      )}

      {/* Error state */}
      {error && (
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
      )}

      {/* Success state */}
      {!loading && !error && (
        <>
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

          {/* Atom details panel */}
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
            </div>
          )}

          {/* Controls */}
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
              <div>🖱️ <strong>Left Click + Drag:</strong> Rotate</div>
              <div>🖱️ <strong>Right Click + Drag:</strong> Move</div>
              <div>🖱️ <strong>Scroll:</strong> Zoom</div>
              <div>⚛️ <strong>Click Atom:</strong> Details</div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
