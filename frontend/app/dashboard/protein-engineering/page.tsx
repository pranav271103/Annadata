"use client";

import React from "react";
import ProteinEngineeringView from "@/components/protein/ProteinEngineeringView";
import { Dna, Globe, History, LineChart } from "lucide-react";

export default function ProteinEngineeringPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight text-[var(--color-text)]">
          Protein Engineering &mdash; <span className="text-[var(--color-primary)]">Biotech AI</span>
        </h1>
        <p className="max-w-4xl text-[var(--color-text-muted)]">
          Revolutionizing Indian agriculture through advanced AI-driven crop protein engineering.
          Optimize crop characteristic proteins against regional climate profiles and 20+ years of historical performance data.
        </p>

        <div className="mt-2 flex flex-wrap items-center gap-4 text-xs font-semibold">
          <div className="flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-[var(--color-text-muted)]">
            <History className="h-3.5 w-3.5 text-blue-500" />
            19K+ Crop Performance Records
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-[var(--color-text-muted)]">
            <Globe className="h-3.5 w-3.5 text-emerald-500" />
            Pan-India Climate Profiling
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-[var(--color-text-muted)]">
            <LineChart className="h-3.5 w-3.5 text-amber-500" />
            Quantum Yield Projections
          </div>
        </div>
      </div>

      {/* Main Content */}
      <ProteinEngineeringView />

      {/* Footer Info */}
      <div className="mt-8 grid gap-6 sm:grid-cols-2">
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10 text-blue-500">
            <Dna className="h-5 w-5" />
          </div>
          <h4 className="mb-2 text-sm font-bold text-[var(--color-text)]">Protein-to-Trait Mapping</h4>
          <p className="text-xs leading-relaxed text-[var(--color-text-muted)]">
            Our proprietary engine maps complex agricultural traits to specific protein structures from the RCSB Protein Data Bank.
            By analyzing these relationships, we identify the most effective genetic candidates for regional adaptation.
          </p>
        </div>

        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
            <LineChart className="h-5 w-5" />
          </div>
          <h4 className="mb-2 text-sm font-bold text-[var(--color-text)]">Validation & Accuracy</h4>
          <p className="text-xs leading-relaxed text-[var(--color-text-muted)]">
            Every recommendation is validated against historical yield data (1997-2020) and real-time stress test simulations
            to ensure predicted improvements are feasible in real-world soil conditions.
          </p>
        </div>
      </div>
    </div>
  );
}
