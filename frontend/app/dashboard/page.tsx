"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "@/components/layout/Sidebar";
import StatusBar from "@/components/layout/StatusBar";
import AlertFeed from "@/components/dashboard/AlertFeed";
import ReportDetail from "@/components/dashboard/ReportDetail";
import StatsPanel from "@/components/dashboard/StatsPanel";
import { connectReportStream, mergeSnapshot, prependReport, useReports } from "@/lib/api";
import type { TriageReport } from "@/types";

// Filter chips map straight to backend severity values (All = no filter).
// The "AIT-LDS" chip in the design was a fabricated demo label — dropped.
const FILTERS = ["All", "Critical", "High", "Medium", "Low"] as const;
type Filter = (typeof FILTERS)[number];

export default function DashboardPage() {
  const [filter, setFilter] = useState<Filter>("All");
  const { data: reports, mutate } = useReports(filter);
  const [selected, setSelected] = useState<string | null>(null);

  // Live-websocket subscription — prepend new reports into the SWR cache.
  // Latest mutate/setSelected/filter captured via refs updated in an effect so
  // the WS subscription itself only opens once on mount.
  const mutateRef = useRef(mutate);
  const selectRef = useRef(setSelected);
  const filterRef = useRef<Filter>(filter);
  useEffect(() => {
    mutateRef.current = mutate;
    selectRef.current = setSelected;
    filterRef.current = filter;
  }, [mutate, setSelected, filter]);

  useEffect(() => {
    const cleanup = connectReportStream({
      onSnapshot: (items) => {
        // hydrate selection with the newest report if the user has not picked one yet
        if (items.length > 0) {
          selectRef.current((prev) => prev ?? items[0].incident_id);
        }
        const f = filterRef.current;
        const filtered = f === "All" ? items : items.filter((r) => r.severity === f);
        mutateRef.current((prev) => mergeSnapshot(prev, filtered), { revalidate: false });
      },
      onReport: (report) => {
        // Respect the active severity filter — server-side SWR is already
        // filtered; streamed reports must obey the same gate or the feed
        // would leak other severities into a Critical-only view.
        const f = filterRef.current;
        if (f !== "All" && report.severity !== f) return;
        mutateRef.current((prev) => prependReport(prev, report), { revalidate: false });
      },
    });
    return cleanup;
  }, []);

  // Selected report — derive with first-list fallback instead of state fixups,
  // so switching filter or SWR revalidation never fights an effect.
  const handleSelect = useCallback((id: string) => setSelected(id), []);

  const currentReport: TriageReport | undefined =
    reports?.find((r) => r.incident_id === selected) ?? reports?.[0];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <div className="h-10 bg-white border-b border-surface-tertiary flex items-center px-4 gap-2 flex-shrink-0">
          <span className="text-[11px] font-bold tracking-widest text-gray-500 uppercase">
            SOC <span className="text-critical">TRIAGE</span>
          </span>
          <div className="flex items-center gap-1.5 ml-1">
            <div className="w-1.5 h-1.5 rounded-full bg-low animate-pulse2" />
            <span className="font-mono text-[9px] font-bold text-low tracking-wider">LIVE</span>
          </div>
          <div className="flex-1" />
          {/* Filter chips */}
          <div className="flex gap-1">
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`font-mono text-[10px] px-2.5 py-1 rounded-full border transition-colors ${
                  filter === f
                    ? "bg-critical-bg border-critical text-critical-text font-semibold"
                    : "border-surface-tertiary text-gray-500 hover:bg-surface"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          <AlertFeed
            reports={reports ?? []}
            selected={selected}
            onSelect={handleSelect}
          />
          <ReportDetail report={currentReport} />
          <StatsPanel />
        </div>

        <StatusBar />
      </div>
    </div>
  );
}