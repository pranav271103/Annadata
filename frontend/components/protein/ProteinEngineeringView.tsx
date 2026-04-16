'use client';

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AlertCircle, Beaker, CheckCircle2, TrendingUp, Shield, FlaskConical } from "lucide-react";
import ProteinEngineering from './ProteinEngineering';
import RecommendationPanel from './RecommendationPanel';
import { API_PREFIXES } from "@/lib/utils";

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
  () => import('./ProteinVisualization'),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[500px] flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--color-border)] border-t-[var(--color-primary)]" />
        <p className="text-sm text-[var(--color-text-muted)]">Loading 3D Viewer...</p>
      </div>
    )
  }
);

const API_BASE = API_PREFIXES.proteinEngineering;

export default function ProteinEngineeringView() {
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

  const handleTraitChange = (trait: string, value: number) => {
    setConfig(prev => ({ ...prev, [trait]: value }));
  };

  const handleCropChange = (crop: string) => setConfig(prev => ({ ...prev, crop }));
  const handleRegionChange = (region: string) => setConfig(prev => ({ ...prev, region }));
  const handleSeasonChange = (season: string) => setConfig(prev => ({ ...prev, season }));

  const handleEngineer = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/engineer-trait`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (!response.ok) throw new Error('Failed to engineer proteins');
      const data = await response.json();
      setResult(data);
      if (data.recommended_proteins?.[0]?.pdb_ids?.[0]) {
        setSelectedProtein(data.recommended_proteins[0].pdb_ids[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
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

  return (
    <div className="grid gap-6 lg:grid-cols-12">
      {/* Sidebar: Config */}
      <div className="lg:col-span-4">
        <Card className="h-full border-[var(--color-border)] bg-[var(--color-surface)]">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                <Beaker className="h-5 w-5" />
              </div>
              <div>
                <CardTitle className="text-lg">Trait Configuration</CardTitle>
                <CardDescription>Optimize crop characteristics</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
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
            {error && (
              <div className="mt-4 flex items-start gap-2 rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error)]/10 p-3 text-sm text-[var(--color-error)]">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>{error}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Main Content: Results */}
      <div className="lg:col-span-8 flex flex-col gap-6">
        {result ? (
          <>
            {/* Stats Overview */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
                <CardContent className="pt-6">
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Yield Increase</span>
                    <div className="flex items-baseline gap-1 text-2xl font-bold text-[var(--color-primary)]">
                      <TrendingUp className="h-5 w-5" />
                      {result.yield_increase_percent.toFixed(1)}%
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
                <CardContent className="pt-6">
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Projected Yield</span>
                    <div className="flex items-baseline gap-1 text-2xl font-bold">
                      {result.projected_yield.toFixed(0)}
                      <span className="text-xs font-normal text-[var(--color-text-muted)]">kg/ha</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
                <CardContent className="pt-6">
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Resilience</span>
                    <div className="flex items-baseline gap-1 text-2xl font-bold text-sky-500">
                      <Shield className="h-5 w-5" />
                      {result.climate_resilience_score.toFixed(0)}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)]">
                <CardContent className="pt-6">
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Feasibility</span>
                    <div className="flex items-baseline gap-1 text-2xl font-bold text-amber-500">
                      <CheckCircle2 className="h-5 w-5" />
                      {result.feasibility_score.toFixed(0)}%
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Analysis Tabs */}
            <Card className="flex-1 border-[var(--color-border)] bg-[var(--color-surface)]">
              <Tabs defaultValue="visualization" className="w-full">
                <div className="border-b border-[var(--color-border)] px-6">
                  <TabsList className="h-14 w-full justify-start gap-4 bg-transparent p-0">
                    <TabsTrigger
                      value="visualization"
                      className="rounded-none border-b-2 border-transparent px-0 py-4 text-sm font-semibold text-[var(--color-text-muted)] data-[state=active]:border-[var(--color-primary)] data-[state=active]:bg-transparent data-[state=active]:text-[var(--color-primary)]"
                    >
                      3D Visualization
                    </TabsTrigger>
                    <TabsTrigger
                      value="recommendations"
                      className="rounded-none border-b-2 border-transparent px-0 py-4 text-sm font-semibold text-[var(--color-text-muted)] data-[state=active]:border-[var(--color-primary)] data-[state=active]:bg-transparent data-[state=active]:text-[var(--color-primary)]"
                    >
                      Recommendations
                    </TabsTrigger>
                  </TabsList>
                </div>

                <TabsContent value="visualization" className="p-6">
                  <div className="mb-4">
                    <h3 className="text-xl font-bold">Interactive 3D Protein Structure</h3>
                    <p className="text-sm text-[var(--color-text-muted)]">Explore molecular properties of {selectedProtein}</p>
                  </div>
                  <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-background)]">
                    {selectedProtein && (
                      <ProteinVisualization
                        proteinId={selectedProtein}
                      />
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="recommendations" className="p-6">
                  <RecommendationPanel result={result} />
                </TabsContent>
              </Tabs>
            </Card>
          </>
        ) : (
          /* Empty State */
          <div className="flex flex-1 flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center">
            <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
              <FlaskConical className="h-10 w-10" />
            </div>
            <h3 className="text-2xl font-bold text-[var(--color-text)]">Ready to Optimize</h3>
            <p className="mt-2 max-w-sm text-[var(--color-text-muted)]">
              Configure crop traits and click <strong>"Engineer Traits"</strong> to generate AI-powered protein recommendations and 3D structures.
            </p>

            <div className="mt-12 grid grid-cols-2 gap-4 sm:grid-cols-4">
              {[
                { icon: "⚛️", label: "Interactive 3D" },
                { icon: "🔗", label: "Bond Analysis" },
                { icon: "🧬", label: "DNA Support" },
                { icon: "📊", label: "ML Analytics" },
              ].map((feature) => (
                <div key={feature.label} className="flex flex-col items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-background)] p-4 transition-colors hover:border-[var(--color-primary)]/50">
                  <span className="text-2xl">{feature.icon}</span>
                  <span className="text-xs font-semibold text-[var(--color-text-muted)]">{feature.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
