import clsx, { type ClassValue } from "clsx";
import type { Severity } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

// Tailwind utility class fragments per severity (port from frontend_design lib/utils.ts).
export const SEV_COLORS: Record<Severity, { dot: string; bg: string; text: string; border: string; pill: string }> = {
  Critical:      { dot: "bg-critical",      bg: "bg-critical-bg",      text: "text-critical-text",      border: "border-critical",      pill: "bg-critical-bg text-critical-text border border-critical" },
  High:          { dot: "bg-high",          bg: "bg-high-bg",          text: "text-high-text",           border: "border-high",          pill: "bg-high-bg text-high-text border border-high" },
  Medium:        { dot: "bg-medium",        bg: "bg-medium-bg",        text: "text-medium-text",         border: "border-medium",        pill: "bg-medium-bg text-medium-text border border-medium" },
  Low:           { dot: "bg-low",            bg: "bg-low-bg",           text: "text-low-text",            border: "border-low",           pill: "bg-low-bg text-low-text border border-low" },
  Informational: { dot: "bg-info",           bg: "bg-info-bg",          text: "text-info-text",           border: "border-info",          pill: "bg-info-bg text-info-text border border-info" },
};

// Raw hex (used for inline styles where Tailwind utilities can't go — recharts,
// dynamic widths, evidence-highlight pop).
export const SEV_HEX: Record<Severity, string> = {
  Critical: "#E24B4A", High: "#BA7517", Medium: "#185FA5", Low: "#3B6D11", Informational: "#534AB7",
};

export const SEV_BG_HEX: Record<Severity, string> = {
  Critical: "#FCEBEB", High: "#FAEEDA", Medium: "#E6F1FB", Low: "#EAF3DE", Informational: "#EEEDFE",
};

export const SEV_TEXT_HEX: Record<Severity, string> = {
  Critical: "#A32D2D", High: "#633806", Medium: "#042C53", Low: "#173404", Informational: "#26215C",
};

export function severityShort(s: Severity): string {
  return { Critical: "CRIT", High: "HIGH", Medium: "MED", Low: "LOW", Informational: "INFO" }[s];
}

export function timeAgo(iso: string): string {
  if (!iso) return "";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}