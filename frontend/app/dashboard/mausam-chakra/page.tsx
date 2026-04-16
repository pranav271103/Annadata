"use client";

import { useEffect, useMemo, useState } from "react";
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
import { CHART_COLORS, CHART_DEFAULTS } from "@/components/dashboard/chart-theme";
import {
  ComposedChart,
  Line,
  Bar,
  Area,
  AreaChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const villages = [
  { code: "PB-LDH-001", name: "Ludhiana, Punjab" },
  { code: "MH-NSK-001", name: "Nashik, Maharashtra" },
  { code: "UP-LKO-001", name: "Lucknow, UP" },
  { code: "KA-MYS-001", name: "Mysuru, Karnataka" },
  { code: "RJ-JPR-001", name: "Jaipur, Rajasthan" },
  { code: "TN-MDU-001", name: "Madurai, Tamil Nadu" },
] as const;

type Village = (typeof villages)[number];

export default function MausamChakraPage() {
  const [selectedVillage, setSelectedVillage] = useState<Village>(villages[0]);
  const [current, setCurrent] = useState<any>(null);
  const [forecast, setForecast] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [advisory, setAdvisory] = useState<any>(null);
  const [stations, setStations] = useState<any[]>([]);
  const [meteogram, setMeteogram] = useState<any[]>([]);

  const chartData = useMemo(
    () =>
      forecast.map((f, i) => ({
        hour: `${i + 1}h`,
        temperature_c: f.temperature_c,
        rainfall_mm: f.rainfall_mm,
        humidity_pct: f.humidity_pct,
      })),
    [forecast],
  );

  useEffect(() => {
    const load = async () => {
      try {
        const [currentRes, forecastRes, alertsRes, advisoryRes, stationsRes] = await Promise.all([
          fetch(`${API_PREFIXES.mausamChakra}/weather/current/${selectedVillage.code}`),
          fetch(`${API_PREFIXES.mausamChakra}/weather/forecast/${selectedVillage.code}?hours=24`),
          fetch(`${API_PREFIXES.mausamChakra}/weather/alerts`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              state: selectedVillage.name.split(", ")[1] ?? "Punjab",
              district: selectedVillage.name.split(", ")[0],
              village_code: selectedVillage.code,
            }),
          }),
          fetch(`${API_PREFIXES.mausamChakra}/advisory/agricultural`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              village_code: selectedVillage.code,
              crop_type: "wheat",
              growth_stage: "vegetative",
            }),
          }),
          fetch(`${API_PREFIXES.mausamChakra}/iot/stations?active_only=true`),
        ]);
        if (currentRes.ok) setCurrent(await currentRes.json());
        if (forecastRes.ok) {
          const data = await forecastRes.json();
          setForecast(data.forecasts ?? []);
        }
        if (alertsRes.ok) {
          const data = await alertsRes.json();
          setAlerts(data.active_alerts ?? []);
        }
        if (advisoryRes.ok) setAdvisory(await advisoryRes.json());
        if (stationsRes.ok) {
          const data = await stationsRes.json();
          setStations(data.stations ?? []);
        }
        // Fetch NCMRWF meteogram
        try {
          const meteoRes = await fetch(`${API_PREFIXES.mausamChakra}/weather/meteogram/${selectedVillage.code}`);
          if (meteoRes.ok) {
            const meteoData = await meteoRes.json();
            setMeteogram((meteoData.forecast ?? []).map((d: any, i: number) => ({
              hour: `${i * 3}h`,
              temp: typeof d.temp === 'number' ? +d.temp.toFixed(1) : d.temperature_c,
              pressure: d.pressure ?? d.pressure_hpa,
              wind: d.wind_speed_kmh ?? 0,
              rain: typeof d.rain === 'number' ? +d.rain.toFixed(2) : d.rainfall_mm ?? 0,
            })));
          }
        } catch { /* meteogram optional */ }
      } catch {
        setCurrent(null);
      }
    };
    void load();
  }, [selectedVillage]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-[var(--color-text)]">
          Mausam Chakra &mdash; Hyper-Local Weather
        </h1>
        <p className="mt-1 text-[var(--color-text-muted)]">
          Field-level weather forecasts with IoT station data fusion, hour-by-hour
          predictions, severe weather alerts, and crop-specific advisories.
        </p>
      </div>

      {/* Village selector */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Select Village</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {villages.map((v) => (
              <Button
                key={v.code}
                size="sm"
                variant={
                  selectedVillage.code === v.code ? "default" : "outline"
                }
                onClick={() => setSelectedVillage(v)}
              >
                {v.name}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Current Weather */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>
              Current Weather &mdash; {selectedVillage.name}
            </CardTitle>
            <Badge>Live</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {[
              {
                label: "Temperature",
                value: current?.temperature_c ?? "--",
                unit: "C",
              },
              {
                label: "Humidity",
                value: current?.humidity_pct ?? "--",
                unit: "%",
              },
              {
                label: "Wind Speed",
                value: current?.wind_speed_kmh ?? "--",
                unit: "km/h",
              },
              {
                label: "Rainfall",
                value: current?.rainfall_mm ?? "--",
                unit: "mm",
              },
              { label: "UV Index", value: current?.uv_index ?? "--", unit: "" },
            ].map((item) => (
              <div
                key={item.label}
                className="flex flex-col items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] p-3"
              >
                <span className="text-xs text-[var(--color-text-muted)]">
                  {item.label}
                </span>
                <span className="mt-1 text-xl font-bold text-[var(--color-text)]">
                  {item.value}
                </span>
                <span className="text-xs text-[var(--color-text-muted)]">
                  {item.unit}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Hourly Forecast + Alerts */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">24-Hour Forecast</CardTitle>
            <CardDescription>
              Hour-by-hour temperature and rain probability
            </CardDescription>
          </CardHeader>
          <CardContent>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart
                  data={chartData}
                  margin={CHART_DEFAULTS.margin}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke={CHART_DEFAULTS.gridStroke}
                  />
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                    stroke={CHART_DEFAULTS.axisStroke}
                  />
                  <YAxis
                    yAxisId="left"
                    tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                    stroke={CHART_DEFAULTS.axisStroke}
                    label={{ value: "°C", position: "insideTopLeft", offset: -5, fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                    stroke={CHART_DEFAULTS.axisStroke}
                    label={{ value: "mm", position: "insideTopRight", offset: -5, fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                  />
                  <Tooltip contentStyle={CHART_DEFAULTS.tooltipStyle} />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="temperature_c"
                    name="Temperature (°C)"
                    stroke={CHART_COLORS.primary}
                    strokeWidth={2}
                    dot={false}
                    animationDuration={CHART_DEFAULTS.animationDuration}
                    animationEasing={CHART_DEFAULTS.animationEasing}
                  />
                  <Bar
                    yAxisId="right"
                    dataKey="rainfall_mm"
                    name="Rainfall (mm)"
                    fill={CHART_COLORS.accent}
                    opacity={0.7}
                    animationDuration={CHART_DEFAULTS.animationDuration}
                    animationEasing={CHART_DEFAULTS.animationEasing}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-background)]">
                <p className="text-sm text-[var(--color-text-muted)]">
                  Loading forecast data&hellip;
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* NCMRWF Meteogram */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">NCMRWF 4km Meteogram</CardTitle>
              <Badge variant="secondary">24hr</Badge>
            </div>
            <CardDescription>
              High-resolution model forecast — Temp, Pressure, Wind, Rain
            </CardDescription>
          </CardHeader>
          <CardContent>
            {meteogram.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={meteogram} margin={CHART_DEFAULTS.margin}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_DEFAULTS.gridStroke} />
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                    stroke={CHART_DEFAULTS.axisStroke}
                  />
                  <YAxis
                    yAxisId="left"
                    tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                    stroke={CHART_DEFAULTS.axisStroke}
                    label={{ value: "\u00b0C / hPa", position: "insideTopLeft", offset: -5, fontSize: 9, fill: CHART_DEFAULTS.axisStroke }}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                    stroke={CHART_DEFAULTS.axisStroke}
                    label={{ value: "mm / km/h", position: "insideTopRight", offset: -5, fontSize: 9, fill: CHART_DEFAULTS.axisStroke }}
                  />
                  <Tooltip contentStyle={CHART_DEFAULTS.tooltipStyle} />
                  <Line yAxisId="left" type="monotone" dataKey="temp" name="Temp (\u00b0C)" stroke={CHART_COLORS.primary} strokeWidth={2} dot={false} />
                  <Line yAxisId="left" type="monotone" dataKey="pressure" name="Pressure (hPa)" stroke="#8884d8" strokeWidth={1} strokeDasharray="5 5" dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="wind" name="Wind (km/h)" stroke={CHART_COLORS.secondary} strokeWidth={1.5} dot={false} />
                  <Bar yAxisId="right" dataKey="rain" name="Rain (mm)" fill={CHART_COLORS.accent} opacity={0.6} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-background)]">
                <p className="text-sm text-[var(--color-text-muted)]">Loading meteogram&hellip;</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Alerts row */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Weather Alerts</CardTitle>
              <Badge variant={alerts.length ? "default" : "secondary"}>
                {alerts.length} Active
              </Badge>
            </div>
            <CardDescription>
              IMD-style severe weather warnings for your area
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm text-[var(--color-text-muted)]">
              {alerts.length ? (
                alerts.slice(0, 3).map((alert, index) => (
                  <li key={`${alert.alert_type}-${index}`} className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-[var(--color-warning)]" />
                    {alert.alert_type}: {alert.severity}
                  </li>
                ))
              ) : (
                <>
                  <li className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" />
                    No active severe weather alerts
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" />
                    No hailstorm warnings
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" />
                    No frost warnings
                  </li>
                </>
              )}
            </ul>
          </CardContent>
        </Card>
      </div>

      {/* Humidity Trend */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Humidity Trend</CardTitle>
          <CardDescription>
            Relative humidity over the next forecast hours
          </CardDescription>
        </CardHeader>
        <CardContent>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={chartData} margin={CHART_DEFAULTS.margin}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke={CHART_DEFAULTS.gridStroke}
                />
                <XAxis
                  dataKey="hour"
                  tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                  stroke={CHART_DEFAULTS.axisStroke}
                />
                <YAxis
                  tick={{ fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                  stroke={CHART_DEFAULTS.axisStroke}
                  domain={[0, 100]}
                  label={{ value: "%", position: "insideTopLeft", offset: -5, fontSize: CHART_DEFAULTS.fontSize, fill: CHART_DEFAULTS.axisStroke }}
                />
                <Tooltip contentStyle={CHART_DEFAULTS.tooltipStyle} />
                <Area
                  type="monotone"
                  dataKey="humidity_pct"
                  name="Humidity (%)"
                  stroke={CHART_COLORS.purple}
                  fill={CHART_COLORS.purple}
                  fillOpacity={0.2}
                  strokeWidth={2}
                  animationDuration={CHART_DEFAULTS.animationDuration}
                  animationEasing={CHART_DEFAULTS.animationEasing}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-background)]">
              <p className="text-sm text-[var(--color-text-muted)]">
                Loading humidity data&hellip;
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Agricultural Advisory */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Agricultural Advisory</CardTitle>
          <CardDescription>
            Weather-based farming recommendations for your crop and growth stage
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              {
                label: "Irrigation",
                desc: "Based on rain forecast and soil moisture",
                value: advisory?.irrigation_recommendation ?? "--",
              },
              {
                label: "Spray Window",
                desc: "Optimal pesticide application time",
                value: advisory?.spray_window ?? "--",
              },
              {
                label: "Harvest Risk",
                desc: "Weather impact on harvest operations",
                value: advisory?.harvest_risk ?? "--",
              },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] p-4"
              >
                <p className="text-sm font-medium text-[var(--color-text)]">
                  {item.label}
                </p>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  {item.desc}
                </p>
                <p className="mt-2 text-lg font-bold text-[var(--color-primary)]">
                  {item.value}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* IoT Stations */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">IoT Weather Stations</CardTitle>
            <Badge variant="outline">Network</Badge>
          </div>
          <CardDescription>
            Registered field-level weather monitoring stations
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3 text-sm text-[var(--color-text-muted)]">
            {stations.length ? (
              stations.slice(0, 3).map((stn) => (
                <li key={stn.station_id} className="flex justify-between">
                  <span>
                    {stn.station_id} &mdash; {stn.district}
                  </span>
                  <Badge variant={stn.status === "active" ? "default" : "secondary"}>
                    {stn.status}
                  </Badge>
                </li>
              ))
            ) : (
              <li className="text-[var(--color-text-muted)]">
                No stations registered
              </li>
            )}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
