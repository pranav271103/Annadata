// UPDATED ProteinEngineering.tsx - ALL CROPS FROM DATASET
// Location: frontend/components/ProteinEngineering.tsx
// REPLACE ENTIRE FILE with this content

'use client';

import React from 'react';

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

  // ALL 22 UNIQUE CROPS FROM YOUR KAGGLE DATASET
  const crops = [
    'Arecanut',
    'Arhar/Tur',
    'Castor seed',
    'Coconut',
    'Cotton(lint)',
    'Dry chillies',
    'Gram',
    'Jute',
    'Linseed',
    'Maize',
    'Mesta',
    'Niger seed',
    'Onion',
    'Other Rabi pulses',
    'Potato',
    'Rapeseed &Mustard',
    'Rice',
    'Sesamum',
    'Small millets',
    'Sugarcane',
    'Sweet potato',
    'Tapioca',
    'Tobacco',
    'Turmeric',
    'Wheat',
    'Bajra',
    'Black pepper',
    'Cardamom',
    'Coriander',
    'Garlic',
    'Ginger',
    'Groundnut',
    'Horse-gram',
    'Jowar',
    'Ragi',
    'Cashewnut',
    'Banana',
    'Soyabean',
    'Barley',
    'Khesari',
    'Masoor',
    'Moong(Green Gram)',
    'Other Kharif pulses',
    'Safflower',
    'Sannhamp',
    'Sunflower',
    'Urad',
    'Peas & beans (Pulses)',
    'other oilseeds',
    'Other Cereals',
    'Cowpea(Lobia)',
    'Oilseeds total',
    'Guar seed',
    'Other Summer Pulses',
    'Moth',
  ];

  // MAJOR INDIAN STATES FROM YOUR DATASET
  const regions = [
    'Andhra Pradesh',
    'Arunachal Pradesh',
    'Assam',
    'Bihar',
    'Chhattisgarh',
    'Goa',
    'Gujarat',
    'Haryana',
    'Himachal Pradesh',
    'Jammu and Kashmir',
    'Jharkhand',
    'Karnataka',
    'Kerala',
    'Madhya Pradesh',
    'Maharashtra',
    'Manipur',
    'Meghalaya',
    'Mizoram',
    'Nagaland',
    'Odisha',
    'Punjab',
    'Rajasthan',
    'Sikkim',
    'Tamil Nadu',
    'Telangana',
    'Tripura',
    'Uttar Pradesh',
    'Uttarakhand',
    'West Bengal',
    'Andaman and Nicobar Islands',
    'Chandigarh',
    'Dadra and Nagar Haveli',
    'Daman and Diu',
    'Delhi',
    'Lakshadweep',
    'Puducherry',
  ];

  const seasons = [
    'Kharif',
    'Rabi', 
    'Whole Year',
    'Autumn',
    'Summer',
    'Winter',
  ];

  return (
    <div style={{ padding: '1.5rem' }}>
      {/* CROP DROPDOWN */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ 
          display: 'block', 
          fontWeight: 600, 
          marginBottom: '0.5rem', 
          fontSize: '0.875rem',
          color: '#374151'
        }}>
          Crop Type
          <span style={{ 
            marginLeft: '0.5rem', 
            fontSize: '0.75rem', 
            color: '#6b7280' 
          }}>
            ({crops.length} crops available)
          </span>
        </label>
        <select
          value={config.crop}
          onChange={(e) => onCropChange(e.target.value)}
          style={{
            width: '100%',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            border: '2px solid #e5e7eb',
            fontSize: '1rem',
            backgroundColor: 'white',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onFocus={(e) => e.target.style.borderColor = '#6366f1'}
          onBlur={(e) => e.target.style.borderColor = '#e5e7eb'}
        >
          {crops.map((crop) => (
            <option key={crop} value={crop}>
              {crop}
            </option>
          ))}
        </select>
      </div>

      {/* REGION DROPDOWN */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ 
          display: 'block', 
          fontWeight: 600, 
          marginBottom: '0.5rem', 
          fontSize: '0.875rem',
          color: '#374151'
        }}>
          State/Region
          <span style={{ 
            marginLeft: '0.5rem', 
            fontSize: '0.75rem', 
            color: '#6b7280' 
          }}>
            ({regions.length} regions)
          </span>
        </label>
        <select
          value={config.region}
          onChange={(e) => onRegionChange(e.target.value)}
          style={{
            width: '100%',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            border: '2px solid #e5e7eb',
            fontSize: '1rem',
            backgroundColor: 'white',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onFocus={(e) => e.target.style.borderColor = '#6366f1'}
          onBlur={(e) => e.target.style.borderColor = '#e5e7eb'}
        >
          {regions.map((region) => (
            <option key={region} value={region}>
              {region}
            </option>
          ))}
        </select>
      </div>

      {/* SEASON DROPDOWN */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ 
          display: 'block', 
          fontWeight: 600, 
          marginBottom: '0.5rem', 
          fontSize: '0.875rem',
          color: '#374151'
        }}>
          Season
        </label>
        <select
          value={config.season}
          onChange={(e) => onSeasonChange(e.target.value)}
          style={{
            width: '100%',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            border: '2px solid #e5e7eb',
            fontSize: '1rem',
            backgroundColor: 'white',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onFocus={(e) => e.target.style.borderColor = '#6366f1'}
          onBlur={(e) => e.target.style.borderColor = '#e5e7eb'}
        >
          {seasons.map((season) => (
            <option key={season} value={season}>
              {season}
            </option>
          ))}
        </select>
      </div>

      {/* TRAIT SLIDERS */}
      <div style={{ 
        marginBottom: '1.5rem', 
        borderTop: '2px solid #e5e7eb', 
        paddingTop: '1.5rem' 
      }}>
        <h3 style={{ 
          fontSize: '1rem', 
          fontWeight: 700, 
          marginBottom: '1rem',
          color: '#111827'
        }}>
          Trait Intensities
        </h3>
        {traits.map((trait) => (
          <div key={trait.key} style={{ marginBottom: '1.25rem' }}>
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              marginBottom: '0.5rem' 
            }}>
              <label style={{ 
                fontSize: '0.875rem', 
                fontWeight: 600,
                color: '#374151'
              }}>
                {trait.label}
              </label>
              <span style={{ 
                fontSize: '0.875rem', 
                color: '#6366f1', 
                fontWeight: 700,
                minWidth: '40px',
                textAlign: 'right'
              }}>
                {config[trait.key]}%
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={config[trait.key]}
              onChange={(e) => onTraitChange(trait.key, parseInt(e.target.value))}
              style={{ 
                width: '100%',
                height: '6px',
                borderRadius: '3px',
                outline: 'none',
                background: `linear-gradient(to right, #6366f1 0%, #6366f1 ${config[trait.key]}%, #e5e7eb ${config[trait.key]}%, #e5e7eb 100%)`,
                WebkitAppearance: 'none',
                cursor: 'pointer',
              }}
            />
          </div>
        ))}
      </div>

      {/* ACTION BUTTONS */}
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <button
          onClick={onEngineer}
          disabled={loading}
          style={{
            flex: 1,
            padding: '0.875rem',
            background: loading ? '#9ca3af' : 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
            color: 'white',
            border: 'none',
            borderRadius: '0.5rem',
            fontWeight: 700,
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '1rem',
            transition: 'all 0.2s',
            boxShadow: loading ? 'none' : '0 4px 6px -1px rgba(99, 102, 241, 0.3)',
          }}
          onMouseEnter={(e) => {
            if (!loading) {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 10px 15px -3px rgba(99, 102, 241, 0.4)';
            }
          }}
          onMouseLeave={(e) => {
            if (!loading) {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 6px -1px rgba(99, 102, 241, 0.3)';
            }
          }}
        >
          {loading ? '⏳ Processing...' : '🧬 Engineer Traits'}
        </button>
        <button
          onClick={onReset}
          disabled={loading}
          style={{
            padding: '0.875rem 1.5rem',
            background: '#f3f4f6',
            color: '#374151',
            border: '2px solid #e5e7eb',
            borderRadius: '0.5rem',
            fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '1rem',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            if (!loading) {
              e.currentTarget.style.background = '#e5e7eb';
              e.currentTarget.style.borderColor = '#d1d5db';
            }
          }}
          onMouseLeave={(e) => {
            if (!loading) {
              e.currentTarget.style.background = '#f3f4f6';
              e.currentTarget.style.borderColor = '#e5e7eb';
            }
          }}
        >
          🔄 Reset
        </button>
      </div>

      {/* INFO NOTE */}
      <div style={{
        marginTop: '1.5rem',
        padding: '1rem',
        background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)',
        borderRadius: '0.5rem',
        border: '1px solid #c7d2fe',
      }}>
        <p style={{
          fontSize: '0.75rem',
          color: '#4338ca',
          margin: 0,
          lineHeight: '1.5',
        }}>
          💡 <strong>Tip:</strong> Data from 19,689 crop records across Indian states (1997-2020)
        </p>
      </div>
    </div>
  );
}
