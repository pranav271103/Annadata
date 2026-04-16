import React from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dna, Target, Lightbulb } from "lucide-react";

interface RecommendationPanelProps {
  result: any;
}

export default function RecommendationPanel({ result }: RecommendationPanelProps) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-xl font-bold">
        <Dna className="h-6 w-6 text-[var(--color-primary)]" />
        <h3>Protein Recommendations</h3>
      </div>

      {/* Recommended Proteins */}
      <div className="grid gap-4">
        {result.recommended_proteins?.map((protein: any, index: number) => (
          <Card key={index} className="border-[var(--color-border)] bg-[var(--color-background)]">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h4 className="text-lg font-bold text-[var(--color-text)]">
                    {protein.trait.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())}
                  </h4>
                  <p className="text-xs text-[var(--color-text-muted)] font-medium">
                    Target Intensity: <span className="text-[var(--color-primary)]">{protein.intensity}%</span>
                  </p>
                </div>
                <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 px-3 py-1 text-xs font-bold">
                  +{protein.yield_contribution.toFixed(1)}% Yield Effect
                </Badge>
              </div>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)] flex items-center gap-1">
                    <Target className="h-3 w-3" /> Candidate Proteins
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {protein.proteins.map((p: string, i: number) => (
                      <Badge key={i} variant="secondary" className="bg-[var(--color-surface)] text-[var(--color-text)] border-[var(--color-border)] text-[10px] font-semibold py-0">
                        {p}
                      </Badge>
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)] flex items-center gap-1">
                    <Dna className="h-3 w-3" /> PDB Accessions
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {protein.pdb_ids.map((id: string, i: number) => (
                      <code key={i} className="rounded bg-sky-500/10 px-2 py-0.5 text-[10px] font-bold text-sky-600 border border-sky-500/20">
                        {id}
                      </code>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-[var(--color-border)]/50">
                <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Biological Mechanism</span>
                <p className="mt-1 text-xs leading-relaxed text-[var(--color-text-muted)]">
                  {protein.mechanism}
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* General Recommendations */}
      {result.recommendations && result.recommendations.length > 0 && (
        <div className="mt-8 space-y-4">
          <div className="flex items-center gap-2 text-base font-bold">
            <Lightbulb className="h-5 w-5 text-amber-500" />
            <h4>Implementation Guidelines</h4>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {result.recommendations.map((rec: string, index: number) => (
              <div
                key={index}
                className="flex items-start gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-xs leading-relaxed text-[var(--color-text-muted)]"
              >
                <div className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                {rec}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
