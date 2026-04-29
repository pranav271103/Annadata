'use client';

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { cn } from "@/lib/utils";

interface ProteinVisualizationProps {
  proteinId: string;
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
    setMounted(true);
  }, []);

  // Load 3Dmol.js script once
  useEffect(() => {
    if (!mounted) return;

    if (typeof window !== 'undefined' && !(window as any).$3Dmol) {
      const script = document.createElement('script');
      script.src = 'https://3Dmol.csb.pitt.edu/build/3Dmol-min.js';
      script.async = true;
      script.onload = () => setScriptLoaded(true);
      script.onerror = () => {
        setError('Failed to load 3Dmol.js library');
        setLoading(false);
      };
      document.head.appendChild(script);
    } else if ((window as any).$3Dmol) {
      setScriptLoaded(true);
    }
  }, [mounted]);

  // Load protein once script is ready AND mounted
  useEffect(() => {
    if (!scriptLoaded || !mounted || !containerRef.current) return;

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
      const container = containerRef.current;
      if (!container) return;

      container.innerHTML = '';

      const viewer = $3Dmol.createViewer(container, { backgroundColor: 'white' });
      viewer.setBackgroundColor(0xffffff, 0); // Set background to transparent via alpha channel

      if (!viewer) {
        setError('Failed to create viewer');
        setLoading(false);
        return;
      }

      viewerRef.current = viewer;

      const pdbUrl = `https://files.rcsb.org/download/${proteinId}.pdb`;

      const timeoutId = setTimeout(() => {
        setError('Loading timeout - server not responding');
        setLoading(false);
      }, 15000);

      fetch(pdbUrl)
        .then((response) => {
          clearTimeout(timeoutId);
          if (!response.ok) throw new Error(`PDB fetch failed: ${response.status}`);
          return response.text();
        })
        .then((pdbData) => {
          viewer.addModel(pdbData, 'pdb');
          viewer.setStyle({}, { cartoon: { color: 'spectrum' } });

          viewer.addStyle({}, {
            stick: {
              radius: 0.15,
              colorscheme: 'Jmol',
            },
          });

          viewer.setClickable(
            {},
            true,
            (atom: any) => {
              if (!atom) return;
              viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
              viewer.addStyle({}, {
                stick: {
                  radius: 0.15,
                  colorscheme: 'Jmol',
                },
              });
              viewer.render();

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

          viewer.zoomTo();
          viewer.render();
          setLoading(false);
        })
        .catch((err) => {
          clearTimeout(timeoutId);
          setError(err.message.includes('404') ? `PDB ID "${proteinId}" not found` : 'Failed to load protein structure');
          setLoading(false);
        });
    } catch (err: any) {
      setError('Failed to initialize viewer');
      setLoading(false);
    }
  }, [scriptLoaded, proteinId, mounted]);

  return (
    <div className="relative w-full">
      <div
        ref={containerRef}
        className={cn(
          "w-full h-[500px] transition-opacity duration-500 rounded-lg overflow-hidden border border-[var(--color-border)] bg-[#0a0a0a]",
          loading || error ? "opacity-0 invisible absolute" : "opacity-100 visible relative"
        )}
      />

      {loading && (
        <div className="flex h-[500px] flex-col items-center justify-center gap-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center animate-pulse">
          <div className="text-5xl animate-bounce">🧬</div>
          <div className="space-y-2">
            <p className="text-lg font-bold text-[var(--color-text)]">Analyzing {proteinId}</p>
            <p className="text-sm text-[var(--color-text-muted)]">Fetching molecular coordinates from RCSB...</p>
          </div>
        </div>
      )}

      {error && (
        <div className="flex h-[500px] flex-col items-center justify-center gap-4 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error)]/5 p-8 text-center">
          <div className="text-4xl">⚠️</div>
          <div className="space-y-1">
            <p className="font-bold text-[var(--color-error)]">{error}</p>
            <p className="text-xs text-[var(--color-error)]/70">Verify the PDB accession at rcsb.org and check your connection.</p>
          </div>
        </div>
      )}

      {!loading && !error && (
        <div className="mt-4 space-y-4">
          <div className="flex items-center justify-between rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3">
            <div className="flex items-center gap-3">
              <span className="text-lg">✅</span>
              <div>
                <p className="text-sm font-bold text-emerald-600">Structure Loaded</p>
                <p className="text-[10px] text-emerald-600/80 uppercase font-black tracking-widest">Active Model: {proteinId}</p>
              </div>
            </div>
            <p className="text-[10px] text-[var(--color-text-muted)] italic text-right">Interactive mode enabled</p>
          </div>

          {atomInfo ? (
            <div className="rounded-xl border border-[var(--color-primary)]/20 bg-[var(--color-primary)]/5 p-5 shadow-inner">
              <div className="flex items-center justify-between mb-4">
                <p className="text-xs font-black uppercase tracking-widest text-[var(--color-primary)] flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[var(--color-primary)] animate-ping" />
                  Atom Selection Inspector
                </p>
                <button onClick={() => setAtomInfo(null)} className="text-[10px] uppercase font-bold text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors">
                  ✕ Clear
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                {[
                  { label: "Element", value: atomInfo.element },
                  { label: "Identity", value: atomInfo.atom },
                  { label: "Residue", value: atomInfo.residueName ? `${atomInfo.residueName} ${atomInfo.residueIndex}` : "-" },
                  { label: "Chain", value: atomInfo.chain },
                  { label: "Serial", value: atomInfo.serial },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-sm">
                    <span className="block text-[8px] font-black uppercase text-[var(--color-text-muted)] mb-1">{item.label}</span>
                    <span className="block text-sm font-bold text-[var(--color-text)]">{item.value || "-"}</span>
                  </div>
                ))}
              </div>

              <div className="mt-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-sm">
                <span className="block text-[8px] font-black uppercase text-[var(--color-text-muted)] mb-1">Spatial Coordinates (Angstroms Å)</span>
                <div className="font-mono text-[10px] text-[var(--color-text)] flex gap-4">
                  <span><strong className="text-[var(--color-primary)]">X:</strong> {atomInfo.x?.toFixed(3)}</span>
                  <span><strong className="text-[var(--color-primary)]">Y:</strong> {atomInfo.y?.toFixed(3)}</span>
                  <span><strong className="text-[var(--color-primary)]">Z:</strong> {atomInfo.z?.toFixed(3)}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/50 p-6 text-center">
              <p className="text-xs text-[var(--color-text-muted)]">Click any part of the 3D model to inspect specific atomic properties</p>
            </div>
          )}

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-sm">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 text-[10px] font-bold text-[var(--color-text-muted)]">
              <div className="flex items-center gap-2 text-blue-500/80 opacity-80"><div className="w-1.5 h-1.5 rounded-full bg-blue-500" /> Rotate: Left + Drag</div>
              <div className="flex items-center gap-2 text-amber-500/80 opacity-80"><div className="w-1.5 h-1.5 rounded-full bg-amber-500" /> Move: Right + Drag</div>
              <div className="flex items-center gap-2 text-emerald-500/80 opacity-80"><div className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Zoom: Scroll</div>
              <div className="flex items-center gap-2 text-rose-500/80 opacity-80"><div className="w-1.5 h-1.5 rounded-full bg-rose-500" /> Inspect: Atom Click</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
