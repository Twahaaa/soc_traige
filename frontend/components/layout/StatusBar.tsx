"use client";

import { useHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_DOT: Record<string, string> = {
  ok: "bg-low",
  warn: "bg-high",
  error: "bg-critical",
};

const STATUS_TEXT: Record<string, string> = {
  ok: "text-low",
  warn: "text-high",
  error: "text-critical",
};

export default function StatusBar() {
  const { data } = useHealth();

  // Loading state — render an empty bar so the layout doesn't shift.
  if (!data) {
    return (
      <div className="h-7 bg-surface-secondary border-t border-surface-tertiary flex items-center px-3 flex-shrink-0">
        <span className="font-mono text-[9px] text-gray-400">connecting to backend…</span>
      </div>
    );
  }

  return (
    <div className="h-7 bg-surface-secondary border-t border-surface-tertiary flex items-center px-3 gap-4 flex-shrink-0 overflow-x-auto whitespace-nowrap">
      {data.components.map((s) => (
        <div key={s.name} className="flex items-center gap-1.5">
          <div className={cn("w-1.5 h-1.5 rounded-full", STATUS_DOT[s.status])} />
          <span className="font-mono text-[9px] text-gray-500">
            {s.name.split(" ")[0]}{" "}
            <span className={cn("font-semibold", STATUS_TEXT[s.status])}>{s.detail}</span>
          </span>
        </div>
      ))}
    </div>
  );
}