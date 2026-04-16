import React from 'react';
import { Button } from "@/components/ui/button";
import { RefreshCw, Zap } from "lucide-react";

interface ProteinEngineeringProps {
  config: any;
  onTraitChange: (trait: string, value: number) => void;
  onCropChange: (crop: string) => void;
  onRegionChange: (region: string) => void;
  onSeasonChange: (season: string) => void;
  onEngineer: () => void;
  onReset: () => void;
  loading: boolean;
}

export default function ProteinEngineering({
  config,
  onTraitChange,
  onCropChange,
  onRegionChange,
  onSeasonChange,
  onEngineer,
  onReset,
  loading,
}: ProteinEngineeringProps) {
  const traits = [
    { key: 'drought_tolerance', label: 'Drought Tolerance' },
    { key: 'heat_resistance', label: 'Heat Resistance' },
    { key: 'disease_resistance', label: 'Disease Resistance' },
    { key: 'salinity_resistance', label: 'Salinity Resistance' },
    { key: 'photosynthesis_efficiency', label: 'Photosynthesis Efficiency' },
    { key: 'nitrogen_efficiency', label: 'Nitrogen Efficiency' },
  ];

  const crops = [
    'Arecanut', 'Arhar/Tur', 'Castor seed', 'Coconut', 'Cotton(lint)', 'Dry chillies', 'Gram', 'Jute', 'Linseed', 'Maize', 'Mesta', 'Niger seed', 'Onion', 'Other Rabi pulses', 'Potato', 'Rapeseed &Mustard', 'Rice', 'Sesamum', 'Small millets', 'Sugarcane', 'Sweet potato', 'Tapioca', 'Tobacco', 'Turmeric', 'Wheat', 'Bajra', 'Black pepper', 'Cardamom', 'Coriander', 'Garlic', 'Ginger', 'Groundnut', 'Horse-gram', 'Jowar', 'Ragi', 'Cashewnut', 'Banana', 'Soyabean', 'Barley', 'Khesari', 'Masoor', 'Moong(Green Gram)', 'Other Kharif pulses', 'Safflower', 'Sannhamp', 'Sunflower', 'Urad', 'Peas & beans (Pulses)', 'other oilseeds', 'Other Cereals', 'Cowpea(Lobia)', 'Oilseeds total', 'Guar seed', 'Other Summer Pulses', 'Moth',
  ];

  const regions = [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Andaman and Nicobar Islands', 'Chandigarh', 'Dadra and Nagar Haveli', 'Daman and Diu', 'Delhi', 'Lakshadweep', 'Puducherry',
  ];

  const seasons = [
    'Kharif', 'Rabi', 'Whole Year', 'Autumn', 'Summer', 'Winter',
  ];

  const inputClass = "mt-1.5 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)] transition-colors";
  const labelClass = "text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider";

  return (
    <div className="space-y-6">
      {/* Selects */}
      <div className="grid gap-4">
        <div>
          <label className={labelClass}>Crop Type</label>
          <select
            value={config.crop}
            onChange={(e) => onCropChange(e.target.value)}
            className={inputClass}
          >
            {crops.map((crop) => <option key={crop} value={crop}>{crop}</option>)}
          </select>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>State/Region</label>
            <select
              value={config.region}
              onChange={(e) => onRegionChange(e.target.value)}
              className={inputClass}
            >
              {regions.map((region) => <option key={region} value={region}>{region}</option>)}
            </select>
          </div>
          <div>
            <label className={labelClass}>Season</label>
            <select
              value={config.season}
              onChange={(e) => onSeasonChange(e.target.value)}
              className={inputClass}
            >
              {seasons.map((season) => <option key={season} value={season}>{season}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* Trait SLiders */}
      <div className="space-y-4 pt-4 border-t border-[var(--color-border)]">
        <h3 className="text-sm font-bold text-[var(--color-text)]">Trait Intensities</h3>
        <div className="grid gap-3">
          {traits.map((trait) => (
            <div key={trait.key} className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="font-medium text-[var(--color-text-muted)]">{trait.label}</span>
                <span className="font-bold text-[var(--color-primary)]">{config[trait.key]}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={config[trait.key]}
                onChange={(e) => onTraitChange(trait.key, parseInt(e.target.value))}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[var(--color-border)] accent-[var(--color-primary)]"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Buttons */}
      <div className="flex flex-col gap-3 pt-4 border-t border-[var(--color-border)]">
        <Button
          onClick={onEngineer}
          disabled={loading}
          className="w-full bg-[var(--color-primary)] hover:bg-[var(--color-primary-dark)] text-white font-bold h-11"
        >
          {loading ? (
            <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Zap className="mr-2 h-4 w-4 fill-current" />
          )}
          {loading ? 'Processing...' : 'Engineer Traits'}
        </Button>
        <Button
          variant="outline"
          onClick={onReset}
          disabled={loading}
          className="w-full border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-border)] h-11 font-semibold"
        >
          Reset Configuration
        </Button>
      </div>

      <div className="rounded-xl border border-[var(--color-primary)]/10 bg-[var(--color-primary)]/5 p-3">
        <p className="text-[10px] leading-relaxed text-[var(--color-primary-dark)] dark:text-[var(--color-primary)]">
          <strong>TIP:</strong> Optimization is based on 19,689 longitudinal crop performance records integrated with regional climate historicals.
        </p>
      </div>
    </div>
  );
}
