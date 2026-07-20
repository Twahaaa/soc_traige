import type { Severity } from "@/types";
import { SEV_COLORS, severityShort, cn } from "@/lib/utils";

export default function SeverityPill({
  severity,
  size = "sm",
}: {
  severity: Severity;
  size?: "xs" | "sm";
}) {
  const c = SEV_COLORS[severity];
  return (
    <span
      className={cn(
        "font-mono font-semibold rounded inline-flex items-center",
        c.pill,
        size === "xs" ? "text-[8px] px-1 py-0.5" : "text-[9px] px-1.5 py-0.5",
      )}
    >
      {severityShort(severity)}
    </span>
  );
}