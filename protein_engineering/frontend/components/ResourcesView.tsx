import React from 'react';

export default function ResourcesView() {
    const resources = [
        {
            title: "Indian Council of Agricultural Research (ICAR)",
            description: "The apex body for coordinating, guiding and managing research and education in agriculture.",
            link: "https://icar.org.in/",
            icon: "🏛️"
        },
        {
            title: "Department of Agriculture & Farmers Welfare",
            description: "Government of India's nodal agency for formulation and administration of the rules and regulations and laws related to agriculture.",
            link: "https://agricoop.nic.in/",
            icon: "🚜"
        },
        {
            title: "RCSB Protein Data Bank",
            description: "A global archive of structural data of biological macromolecules.",
            link: "https://www.rcsb.org/",
            icon: "🧬"
        },
        {
            title: "Pradhan Mantri Fasal Bima Yojana (PMFBY)",
            description: "Crop insurance scheme to provide financial support to farmers suffering crop loss/damage.",
            link: "https://pmfby.gov.in/",
            icon: "🛡️"
        }
    ];

    return (
        <div className="resources-view ux4g-shell">
            <h2 className="section-title" style={{ marginTop: '2rem' }}>Resources & References</h2>
            <p className="section-subtitle">Useful links for farmers, researchers, and policymakers.</p>

            <div className="resources-grid">
                {resources.map((resource, index) => (
                    <a key={index} href={resource.link} target="_blank" rel="noopener noreferrer" className="resource-card">
                        <div className="resource-icon">{resource.icon}</div>
                        <div className="resource-content">
                            <h3 className="resource-title">{resource.title}</h3>
                            <p className="resource-description">{resource.description}</p>
                        </div>
                        <div className="resource-arrow">↗</div>
                    </a>
                ))}
            </div>
        </div>
    );
}
