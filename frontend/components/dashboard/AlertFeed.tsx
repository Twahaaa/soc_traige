"use client";

import type { TriageReport } from "@/types";
import { SEV_COLORS, cn } from "@/lib/utils";
import SeverityPill from "@/components/ui/SeverityPill";

function timeLabel(iso: string): string {
  if (!iso) return "";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000 / 60);
  if (diff < 1) return "just now";
  if (diff < 60) return `${diff}m ago`;
  return `${Math.floor(diff / 60)}h ago`;
}

interface Props {
  reports: TriageReport[];
  selected: string | null;
  onSelect: (id: string) => void;
}

export default function AlertFeed({ reports, selected, onSelect }: Props) {
  return (
    <div className="w-60 flex-shrink-0 border-r border-surface-tertiary flex flex-col overflow-hidden">
      {/* Header */}
      <div className="h-8 bg-surface-secondary border-b border-surface-tertiary flex items-center px-3 gap-2 flex-shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Alerts</span>
        <span className="font-mono text-[10px] bg-white border border-surface-tertiary rounded-full px-2 text-gray-500">
          {reports.length} active
        </span>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {reports.length === 0 && (
          <div className="px-3 py-4 font-mono text-[10px] text-gray-400">No alerts.</div>
        )}
        {reports.map((r, i) => {
          const isSelected = r.incident_id === selected;
          const c = SEV_COLORS[r.severity];
          const isNew = i < 2;
          return (
            <div
              key={r.incident_id}
              data-testid="alert-feed-item"
              data-incident-id={r.incident_id}
              data-severity={r.severity}
              data-title={r.title}
              onClick={() => onSelect(r.incident_id)}
              className={cn(
                "px-3 py-2 border-b border-surface-tertiary cursor-pointer flex gap-2 transition-colors",
                isSelected ? `${c.bg} border-l-2 ${c.border} pl-2.5` : "hover:bg-surface",
              )}
            >
              {/* Severity dot */}
              <div className={cn("w-2 h-2 rounded-full flex-shrink-0 mt-1", c.dot)} />
              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-medium leading-tight truncate">{r.title}</div>
                <div className="flex gap-1.5 mt-1">
                  <span className="font-mono text-[9px] text-gray-400">{r.affected_host}</span>
                  <span className="font-mono text-[9px] text-gray-300">·</span>
                  <span className="font-mono text-[9px] text-gray-400">{r.log_source}</span>
                  <span className="font-mono text-[9px] text-gray-300">·</span>
                  <span className="font-mono text-[9px] text-gray-400">{timeLabel(r.timestamp)}</span>
                </div>
              </div>
              {/* Pill + new tag */}
              <div className="flex flex-col items-end gap-1 flex-shrink-0">
                <SeverityPill severity={r.severity} size="xs" />
                {isNew && (
                  <span className="font-mono text-[8px] bg-critical text-white px-1 py-0.5 rounded font-bold animate-blink">
                    NEW
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}