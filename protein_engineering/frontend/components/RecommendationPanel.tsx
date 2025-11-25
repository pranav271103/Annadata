'use client';

import React from 'react';

interface RecommendationPanelProps {
  result: any;
}

export default function RecommendationPanel({ result }: RecommendationPanelProps) {
  return (
    <div style={{ padding: '1.5rem' }}>
      <h3 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '1rem' }}>
        Protein Recommendations
      </h3>

      {/* Recommended Proteins */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {result.recommended_proteins?.map((protein: any, index: number) => (
          <div
            key={index}
            style={{
              background: '#f9fafb',
              borderRadius: '0.75rem',
              padding: '1.5rem',
              border: '2px solid #e5e7eb',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
              <div>
                <h4 style={{ fontSize: '1.125rem', fontWeight: 700, color: '#111827', marginBottom: '0.5rem' }}>
                  {protein.trait.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())}
                </h4>
                <p style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                  Intensity: <strong>{protein.intensity}%</strong>
                </p>
              </div>
              <div style={{
                background: '#dcfce7',
                color: '#166534',
                padding: '0.5rem 1rem',
                borderRadius: '9999px',
                fontSize: '0.875rem',
                fontWeight: 700,
              }}>
                +{protein.yield_contribution.toFixed(1)}% Yield
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.5rem' }}>
                Proteins:
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {protein.proteins.map((p: string, i: number) => (
                  <span
                    key={i}
                    style={{
                      background: 'white',
                      padding: '0.25rem 0.75rem',
                      borderRadius: '0.375rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      border: '1px solid #d1d5db',
                    }}
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.5rem' }}>
                PDB IDs:
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {protein.pdb_ids.map((id: string, i: number) => (
                  <span
                    key={i}
                    style={{
                      background: '#eef2ff',
                      color: '#4338ca',
                      padding: '0.25rem 0.75rem',
                      borderRadius: '0.375rem',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      fontFamily: 'monospace',
                    }}
                  >
                    {id}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.5rem' }}>
                Mechanism:
              </p>
              <p style={{ fontSize: '0.875rem', color: '#4b5563', lineHeight: '1.6' }}>
                {protein.mechanism}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* General Recommendations */}
      {result.recommendations && result.recommendations.length > 0 && (
        <div style={{ marginTop: '2rem' }}>
          <h4 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: '1rem' }}>
            Implementation Guidelines
          </h4>
          <ul style={{ listStyleType: 'disc', paddingLeft: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {result.recommendations.map((rec: string, index: number) => (
              <li key={index} style={{ fontSize: '0.875rem', color: '#4b5563', lineHeight: '1.6' }}>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
