import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes without style conflicts.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a number as Indian Rupee currency.
 */
export function formatPrice(price: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(price);
}

/**
 * Format a date string into a human-readable format (e.g. "27 Feb 2026").
 */
export function formatDate(date: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(date));
}

/**
 * Direct backend URLs for each microservice.
 * Used for server-side calls or health checks.
 * Client-side calls should go through the Next.js rewrites (e.g. /api/msp-mitra/...).
 */
export const API_URLS = {
  mspMitra:
    process.env.NEXT_PUBLIC_MSP_MITRA_URL || "http://localhost:8001",
  soilscan:
    process.env.NEXT_PUBLIC_SOILSCAN_URL || "http://localhost:8002",
  fasalRakshak:
    process.env.NEXT_PUBLIC_FASAL_RAKSHAK_URL || "http://localhost:8003",
  jalShakti:
    process.env.NEXT_PUBLIC_JAL_SHAKTI_URL || "http://localhost:8004",
  harvestShakti:
    process.env.NEXT_PUBLIC_HARVEST_SHAKTI_URL || "http://localhost:8005",
  kisaanSahayak:
    process.env.NEXT_PUBLIC_KISAAN_SAHAYAK_URL || "http://localhost:8006",
  proteinEngineering:
    process.env.NEXT_PUBLIC_PROTEIN_ENGINEERING_URL || "http://localhost:8007",
  kisanCredit:
    process.env.NEXT_PUBLIC_KISAN_CREDIT_URL || "http://localhost:8008",
  harvestToCart:
    process.env.NEXT_PUBLIC_HARVEST_TO_CART_URL || "http://localhost:8009",
  beejSuraksha:
    process.env.NEXT_PUBLIC_BEEJ_SURAKSHA_URL || "http://localhost:8010",
  mausamChakra:
    process.env.NEXT_PUBLIC_MAUSAM_CHAKRA_URL || "http://localhost:8011",
  gamification:
    process.env.NEXT_PUBLIC_GAMIFICATION_URL || "http://localhost:8012",
  brainService:
    process.env.NEXT_PUBLIC_BRAIN_SERVICE_URL || "http://localhost:8013",
} as const;

/**
 * Rewrite-based prefixes for client-side API calls.
 * These route through Next.js rewrites defined in next.config.ts.
 */
export const API_PREFIXES = {
  mspMitra:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/msp-mitra",
  soilscan:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/soilscan",
  fasalRakshak:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/fasal-rakshak",
  jalShakti:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/jal-shakti",
  harvestShakti:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/harvest-shakti",
  kisaanSahayak:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/kisaan-sahayak",
  proteinEngineering:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/protein-engineering",
  kisanCredit:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/kisan-credit",
  harvestToCart:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/harvest-to-cart",
  beejSuraksha:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/beej-suraksha",
  mausamChakra:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/mausam-chakra",
  gamification:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/gamification",
  brainService:
    (process.env.NEXT_PUBLIC_API_BASE_URL || "") + "/api/brain-service",
} as const;
