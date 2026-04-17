import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // Service API rewrites — route frontend API calls to backend services
  async rewrites() {
    return [
      // Auth routes — proxied to MSP Mitra (all services share the same auth)
      {
        source: "/api/auth/:path*",
        destination: `${process.env.NEXT_PUBLIC_MSP_MITRA_URL || "http://localhost:8001"}/auth/:path*`,
      },
      {
        source: "/api/msp-mitra/:path*",
        destination: `${process.env.NEXT_PUBLIC_MSP_MITRA_URL || "http://localhost:8001"}/:path*`,
      },
      {
        source: "/api/soilscan/:path*",
        destination: `${process.env.NEXT_PUBLIC_SOILSCAN_URL || "http://localhost:8002"}/:path*`,
      },
      {
        source: "/api/fasal-rakshak/:path*",
        destination: `${process.env.NEXT_PUBLIC_FASAL_RAKSHAK_URL || "http://localhost:8003"}/:path*`,
      },
      {
        source: "/api/jal-shakti/:path*",
        destination: `${process.env.NEXT_PUBLIC_JAL_SHAKTI_URL || "http://localhost:8004"}/:path*`,
      },
      {
        source: "/api/harvest-shakti/:path*",
        destination: `${process.env.NEXT_PUBLIC_HARVEST_SHAKTI_URL || "http://localhost:8005"}/:path*`,
      },
      {
        source: "/api/kisaan-sahayak/:path*",
        destination: `${process.env.NEXT_PUBLIC_KISAAN_SAHAYAK_URL || "http://localhost:8006"}/:path*`,
      },
      {
        source: "/api/protein-engineering/:path*",
        destination: `${process.env.NEXT_PUBLIC_PROTEIN_ENGINEERING_URL || "http://localhost:8007"}/:path*`,
      },
      {
        source: "/api/kisan-credit/:path*",
        destination: `${process.env.NEXT_PUBLIC_KISAN_CREDIT_URL || "http://localhost:8008"}/:path*`,
      },
      {
        source: "/api/harvest-to-cart/:path*",
        destination: `${process.env.NEXT_PUBLIC_HARVEST_TO_CART_URL || "http://localhost:8009"}/:path*`,
      },
      {
        source: "/api/beej-suraksha/:path*",
        destination: `${process.env.NEXT_PUBLIC_BEEJ_SURAKSHA_URL || "http://localhost:8010"}/:path*`,
      },
      {
        source: "/api/mausam-chakra/:path*",
        destination: `${process.env.NEXT_PUBLIC_MAUSAM_CHAKRA_URL || "http://localhost:8011"}/:path*`,
      },
      // Gamification service
      {
        source: "/api/gamification/:path*",
        destination: `${process.env.NEXT_PUBLIC_GAMIFICATION_URL || "http://localhost:8012"}/:path*`,
      },
      // Brain Service (Agentic Orchestrator)
      {
        source: "/api/brain-service/:path*",
        destination: `${process.env.NEXT_PUBLIC_BRAIN_SERVICE_URL || "http://localhost:8013"}/:path*`,
      },

    ];
  },
};

export default nextConfig;
