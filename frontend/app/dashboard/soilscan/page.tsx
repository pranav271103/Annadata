"use client";

import { useMemo, useState } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { API_PREFIXES } from "@/lib/utils";
import {
  RadialBarChart,
  RadialBar,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";
import {
  CHART_COLORS,
  CHART_DEFAULTS,
  getScoreColor,
} from "@/components/dashboard/chart-theme";

type SoilAnalysisResponse = {
  analysis_id: string;
  plot_id: string;
  latitude: number;
  longitude: number;
  soil_type: string | null;
  temperature_celsius: number | null;
  nitrogen_ppm: number;
  phosphorus_ppm: number;
  potassium_ppm: number;
  ph_level: number;
  organic_carbon_pct: number;
  moisture_pct: number;
  health_score: number;
  fertility_class: "poor" | "moderate" | "good" | "excellent";
  recommendations: { nutrient: string; status: string; message: string }[];
  analyzed_at: string;
};

type QuantumCorrelationResponse = {
  correlations: { parameters: string[]; correlation_coefficient: number; insight: string; confidence: number }[];
  interventions: { priority: number; action: string; rationale: string; expected_impact: string }[];
  quantum_metrics: { qubits_used: number; circuit_depth: number; classical_time_ms: number; quantum_time_ms: number; speedup_factor: number };
};

export default function SoilScanPage() {
  const [plotId, setPlotId] = useState("plot-001");
  const [soilType, setSoilType] = useState("loamy");
  const [nitrogen, setNitrogen] = useState("48");
  const [phosphorus, setPhosphorus] = useState("22");
  const [potassium, setPotassium] = useState("110");
  const [phLevel, setPhLevel] = useState("6.7");
  const [organicCarbon, setOrganicCarbon] = useState("0.8");
  const [moisture, setMoisture] = useState("24");
  const [analysis, setAnalysis] = useState<SoilAnalysisResponse | null>(null);
  const [quantum, setQuantum] = useState<QuantumCorrelationResponse | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  const healthBadge = useMemo(() => {
    if (!analysis) return { label: "Pending", variant: "outline" as const };
    if (analysis.fertility_class === "excellent" || analysis.fertility_class === "good") {
      return { label: analysis.fertility_class.toUpperCase(), variant: "default" as const };
    }
    return { label: analysis.fertility_class.toUpperCase(), variant: "secondary" as const };
  }, [analysis]);

  const gaugeData = useMemo(() => {
    if (!analysis) return null;
    const color = getScoreColor(analysis.health_score, 100);
    return {
      data: [
        { name: "score", value: analysis.health_score, fill: color },
      ],
      color,
    };
  }, [analysis]);

  const radarData = useMemo(() => {
    if (!analysis) return null;
    return [
      {
        nutrient: "Nitrogen",
        value: analysis.nitrogen_ppm,
        fullMark: 100,
      },
      {
        nutrient: "Phosphorus",
        value: analysis.phosphorus_ppm,
        fullMark: 50,
      },
      {
        nutrient: "Potassium",
        value: analysis.potassium_ppm,
        fullMark: 200,
      },
      {
        nutrient: "pH",
        value: analysis.ph_level,
        fullMark: 14,
      },
      {
        nutrient: "Organic C",
        value: analysis.organic_carbon_pct,
        fullMark: 2,
      },
    ];
  }, [analysis]);

  async function runAnalysis() {
    setStatus("loading");
    try {
      const res = await fetch(`${API_PREFIXES.soilscan}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plot_id: plotId,
          latitude: 28.61,
          longitude: 77.21,
          nitrogen_ppm: Number(nitrogen),
          phosphorus_ppm: Number(phosphorus),
          potassium_ppm: Number(potassium),
          ph_level: Number(phLevel),
          organic_carbon_pct: Number(organicCarbon),
          moisture_pct: Number(moisture),
          temperature_celsius: 28,
          soil_type: soilType,
        }),
      });
      if (!res.ok) throw new Error("Soil analysis failed");
      const data = (await res.json()) as SoilAnalysisResponse;
      setAnalysis(data);

      const qc = await fetch(`${API_PREFIXES.soilscan}/quantum-correlation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nitrogen_ppm: Number(nitrogen),
          phosphorus_ppm: Number(phosphorus),
          potassium_ppm: Number(potassium),
          ph: Number(phLevel),
          moisture_pct: Number(moisture),
          organic_carbon_pct: Number(organicCarbon),
          soil_type: soilType,
          region: "north_india",
        }),
      });
      if (qc.ok) {
        const qcData = (await qc.json()) as QuantumCorrelationResponse;
        setQuantum(qcData);
      } else {
        setQuantum(null);
      }
      setStatus("idle");
    } catch (err: any) {
      setErrorDetail(err.message || "Analysis failed");
      setStatus("error");
    }
  }

  async function runLiveScan() {
    setStatus("loading");
    setErrorDetail(null);
    try {
      const res = await fetch(`${API_PREFIXES.soilscan}/live-scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plot_id: plotId,
          latitude: 28.61,
          longitude: 77.21,
          soil_type: soilType,
          region: "north_india",
        }),
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Live scan failed");
      }
      const data = (await res.json()) as SoilAnalysisResponse;
      setAnalysis(data);

      // Update the input fields with the "scanned" values to match the illusion
      setNitrogen(data.nitrogen_ppm.toFixed(1));
      setPhosphorus(data.phosphorus_ppm.toFixed(1));
      setPotassium(data.potassium_ppm.toFixed(1));
      setPhLevel(data.ph_level.toFixed(1));
      setOrganicCarbon(data.organic_carbon_pct.toFixed(2));
      setMoisture(data.moisture_pct.toFixed(0));

      // We still run quantum correlation for the extra data
      const qc = await fetch(`${API_PREFIXES.soilscan}/quantum-correlation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nitrogen_ppm: data.nitrogen_ppm,
          phosphorus_ppm: data.phosphorus_ppm,
          potassium_ppm: data.potassium_ppm,
          ph: data.ph_level,
          moisture_pct: data.moisture_pct,
          organic_carbon_pct: data.organic_carbon_pct,
          soil_type: soilType,
          region: "north_india",
        }),
      });
      if (qc.ok) {
        const qcData = (await qc.json()) as QuantumCorrelationResponse;
        setQuantum(qcData);
      }
      setStatus("idle");
    } catch (err: any) {
      setErrorDetail(err.message || "Live scan failed");
      setStatus("error");
    }
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-[var(--color-text)]">
          SoilScan AI &mdash; Soil Health Analysis
        </h1>
        <p className="mt-1 text-[var(--color-text-muted)]">
          Upload soil images or satellite data to receive AI-driven soil health
          assessments, nutrient mapping, and amendment recommendations.
        </p>
      </div>

      {/* Upload section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload Soil Data</CardTitle>
          <CardDescription>
            Enter plot metrics and run AI analysis
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Plot ID
              </label>
              <input
                value={plotId}
                onChange={(event) => setPlotId(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Soil Type
              </label>
              <input
                value={soilType}
                onChange={(event) => setSoilType(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Nitrogen (ppm)
              </label>
              <input
                value={nitrogen}
                onChange={(event) => setNitrogen(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Phosphorus (ppm)
              </label>
              <input
                value={phosphorus}
                onChange={(event) => setPhosphorus(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Potassium (ppm)
              </label>
              <input
                value={potassium}
                onChange={(event) => setPotassium(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                pH Level
              </label>
              <input
                value={phLevel}
                onChange={(event) => setPhLevel(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Organic Carbon (%)
              </label>
              <input
                value={organicCarbon}
                onChange={(event) => setOrganicCarbon(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--color-text-muted)]">
                Moisture (%)
              </label>
              <input
                value={moisture}
                onChange={(event) => setMoisture(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <Button onClick={runAnalysis} disabled={status === "loading"}>
              {status === "loading" ? "Analyzing..." : "Run Analysis"}
            </Button>
            <Button
              variant="outline"
              onClick={runLiveScan}
              disabled={status === "loading"}
              className="border-[var(--color-primary)] text-[var(--color-primary)] hover:bg-[var(--color-primary)] hover:text-white"
            >
              {status === "loading" ? "Scanning Hardware..." : "Start Live Scan"}
            </Button>
            {status === "error" ? (
              <span className="text-sm text-[var(--color-error)]">
                {errorDetail || "Unable to fetch soil analysis. Check the API and Arduino connection."}
              </span>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {/* Results grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* Soil health score */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Soil Health Score</CardTitle>
              <Badge variant={healthBadge.variant}>{healthBadge.label}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            {analysis && gaugeData ? (
              <div className="flex flex-col items-center gap-2">
                <div className="relative" style={{ width: 160, height: 160 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <RadialBarChart
                      cx="50%"
                      cy="50%"
                      innerRadius="70%"
                      outerRadius="90%"
                      startAngle={90}
                      endAngle={-270}
                      barSize={12}
                      data={gaugeData.data}
                    >
                      <RadialBar
                        background={{ fill: "var(--color-border, #e7e5e4)" }}
                        dataKey="value"
                        cornerRadius={6}
                        animationDuration={CHART_DEFAULTS.animationDuration}
                        animationEasing={CHART_DEFAULTS.animationEasing}
                      />
                    </RadialBarChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span
                      className="text-2xl font-bold"
                      style={{ color: gaugeData.color }}
                    >
                      {analysis.health_score.toFixed(0)}
                    </span>
                    <span className="text-xs text-[var(--color-text-muted)] capitalize">
                      {analysis.fertility_class}
                    </span>
                  </div>
                </div>
                <p className="text-xs text-[var(--color-text-muted)]">
                  Analyzed at {new Date(analysis.analyzed_at).toLocaleString()}
                </p>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-background)]">
                <p className="text-sm text-[var(--color-text-muted)]">
                  Run analysis to generate score
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Nutrient analysis */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Nutrient Analysis</CardTitle>
          </CardHeader>
          <CardContent>
            {radarData ? (
              <div className="flex flex-col items-center">
                <div style={{ width: 250, height: 250 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart
                      cx="50%"
                      cy="50%"
                      outerRadius="75%"
                      data={radarData}
                    >
                      <PolarGrid stroke={CHART_DEFAULTS.gridStroke} />
                      <PolarAngleAxis
                        dataKey="nutrient"
                        tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                      />
                      <PolarRadiusAxis
                        angle={90}
                        tick={false}
                        axisLine={false}
                      />
                      <Radar
                        name="Value"
                        dataKey="value"
                        stroke={CHART_COLORS.primary}
                        fill={CHART_COLORS.primary}
                        fillOpacity={0.3}
                        animationDuration={CHART_DEFAULTS.animationDuration}
                        animationEasing={CHART_DEFAULTS.animationEasing}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
                <ul className="mt-2 w-full space-y-1 text-xs text-[var(--color-text-muted)]">
                  <li className="flex justify-between">
                    <span>N</span>
                    <span className="font-medium text-[var(--color-text)]">{analysis!.nitrogen_ppm.toFixed(1)} ppm</span>
                  </li>
                  <li className="flex justify-between">
                    <span>P</span>
                    <span className="font-medium text-[var(--color-text)]">{analysis!.phosphorus_ppm.toFixed(1)} ppm</span>
                  </li>
                  <li className="flex justify-between">
                    <span>K</span>
                    <span className="font-medium text-[var(--color-text)]">{analysis!.potassium_ppm.toFixed(1)} ppm</span>
                  </li>
                  <li className="flex justify-between">
                    <span>pH</span>
                    <span className="font-medium text-[var(--color-text)]">{analysis!.ph_level.toFixed(2)}</span>
                  </li>
                  <li className="flex justify-between">
                    <span>OC</span>
                    <span className="font-medium text-[var(--color-text)]">{analysis!.organic_carbon_pct.toFixed(2)}%</span>
                  </li>
                </ul>
              </div>
            ) : (
              <ul className="space-y-2 text-sm text-[var(--color-text-muted)]">
                <li className="flex justify-between">
                  <span>Nitrogen (ppm)</span>
                  <span className="font-medium text-[var(--color-text)]">--</span>
                </li>
                <li className="flex justify-between">
                  <span>Phosphorus (ppm)</span>
                  <span className="font-medium text-[var(--color-text)]">--</span>
                </li>
                <li className="flex justify-between">
                  <span>Potassium (ppm)</span>
                  <span className="font-medium text-[var(--color-text)]">--</span>
                </li>
                <li className="flex justify-between">
                  <span>Organic Carbon (%)</span>
                  <span className="font-medium text-[var(--color-text)]">--</span>
                </li>
                <li className="flex justify-between">
                  <span>pH Level</span>
                  <span className="font-medium text-[var(--color-text)]">--</span>
                </li>
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Recommendations */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recommendations</CardTitle>
            <CardDescription>
              AI-generated amendment suggestions
            </CardDescription>
          </CardHeader>
          <CardContent>
            {analysis ? (
              <ul className="space-y-2 text-sm text-[var(--color-text-muted)]">
                {analysis.recommendations.slice(0, 4).map((rec, index) => (
                  <li key={`${rec.nutrient}-${index}`} className="flex flex-col gap-1">
                    <span className="text-[var(--color-text)]">
                      {rec.nutrient} - {rec.status}
                    </span>
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {rec.message}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-background)]">
                <p className="text-sm text-[var(--color-text-muted)]">
                  Recommendations will appear after analysis
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Advanced Analysis Endpoints */}
      <div className="grid gap-4 sm:grid-cols-2">
        {/* Photo-Based Analysis */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Photo-Based Analysis</CardTitle>
            <CardDescription>
              Analyze soil properties from photo-derived color and texture data
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--color-text-muted)]">
              Submit soil color in HSV format and texture classification to
              receive ML-predicted soil properties including organic matter
              content, moisture levels, and composition estimates.
            </p>
            <ul className="mt-3 space-y-1.5 text-sm text-[var(--color-text-muted)]">
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                HSV color space input for consistent soil color representation
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Texture classification (sandy, loamy, clay, silt)
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                Returns predicted nutrient profile and soil health indicators
              </li>
            </ul>
            <div className="mt-4">
              <code className="rounded bg-[var(--color-background)] px-2 py-1 text-xs text-[var(--color-text-muted)] border border-[var(--color-border)]">
                POST /analyze-photo
              </code>
            </div>
          </CardContent>
        </Card>

        {/* Quantum ML Correlations */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Quantum ML Correlations</CardTitle>
            <CardDescription>
              Discover hidden correlations in soil data using quantum-inspired ML
            </CardDescription>
          </CardHeader>
          <CardContent>
            {quantum ? (
              <div className="space-y-3">
                <div className="text-xs text-[var(--color-text-muted)]">
                  Speedup: {quantum.quantum_metrics.speedup_factor}x -
                  Qubits: {quantum.quantum_metrics.qubits_used} - Depth: {quantum.quantum_metrics.circuit_depth}
                </div>
                <ul className="space-y-2 text-sm text-[var(--color-text-muted)]">
                  {quantum.correlations.slice(0, 3).map((c, index) => (
                    <li key={`${c.parameters.join("-")}-${index}`}>
                      <span className="text-[var(--color-text)]">
                        {c.parameters.join(" - ")}
                      </span>
                      : {c.insight}
                    </li>
                  ))}
                </ul>
                <div className="pt-2 text-xs text-[var(--color-text-muted)]">
                  Top intervention: {quantum.interventions[0]?.action}
                </div>
              </div>
            ) : (
              <p className="text-sm text-[var(--color-text-muted)]">
                Run a soil analysis to see quantum correlation insights.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
