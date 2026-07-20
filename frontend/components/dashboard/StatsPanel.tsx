"use client";

import { useStats } from "@/lib/api";
import { SEV_HEX, SEV_BG_HEX } from "@/lib/utils";
import type { Severity } from "@/types";

const SEV_ORDER: Severity[] = ["Critical", "High", "Medium", "Low", "Informational"];
const SEV_SHORT: Record<Severity, string> = {
  Critical: "CRIT", High: "HIGH", Medium: "MED", Low: "LOW", Informational: "INFO",
};

function StatCard({ children }: { children: React.ReactNode }) {
  return <div className="bg-surface rounded-lg p-2.5">{children}</div>;
}

function CardLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[9px] uppercase tracking-wider text-gray-400 font-semibold mb-1.5">
      {children}
    </div>
  );
}

export default function StatsPanel() {
  const { data } = useStats();

  if (!data) {
    return (
      <div className="w-44 flex-shrink-0 border-l border-surface-tertiary flex flex-col overflow-hidden">
        <div className="h-8 bg-surface-secondary border-b border-surface-tertiary flex items-center px-3 flex-shrink-0">
          <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Overview</span>
        </div>
        <div className="flex-1 overflow-y-auto p-2.5 font-mono text-[10px] text-gray-400">
          loading…
        </div>
      </div>
    );
  }

  const total = data.total_alerts_all || 1;
  const showedSevs = SEV_ORDER.filter((s) => data.severity_distribution[s] !== undefined);

  return (
    <div className="w-44 flex-shrink-0 border-l border-surface-tertiary flex flex-col overflow-hidden">
      <div className="h-8 bg-surface-secondary border-b border-surface-tertiary flex items-center px-3 flex-shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Overview</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2.5 flex flex-col gap-2">
        {/* Total Alerts */}
        <StatCard>
          <CardLabel>Total Alerts (24h)</CardLabel>
          <div className="text-2xl font-bold leading-none mb-1" data-testid="total-alerts-24h">
            {data.total_alerts_24h}
          </div>
          <div className="font-mono text-[9px] text-gray-400">{data.total_alerts_all} all-time</div>
        </StatCard>

        {/* Severity Split */}
        <StatCard>
          <CardLabel>Severity Split</CardLabel>
          {showedSevs.map((sev) => {
            const count = data.severity_distribution[sev] ?? 0;
            return (
              <div key={sev} className="flex items-center gap-1.5 mb-1.5">
                <div className="font-mono text-[8px] text-gray-400 w-7">{SEV_SHORT[sev]}</div>
                <div
                  className="flex-1 h-1 rounded-full overflow-hidden"
                  style={{ background: SEV_BG_HEX[sev] }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${(count / total) * 100}%`, background: SEV_HEX[sev] }}
                  />
                </div>
                <div className="font-mono text-[9px] text-gray-500 w-5 text-right">{count}</div>
              </div>
            );
          })}
        </StatCard>

        {/* Top MITRE TTPs */}
        {data.top_mitre.length > 0 && (
          <StatCard>
            <CardLabel>Top MITRE TTPs</CardLabel>
            {data.top_mitre.map((m) => (
              <div key={m.technique_id} className="flex justify-between items-center mb-1.5">
                <span className="text-[9px] text-gray-600 truncate flex-1 pr-1">
                  {m.technique_id} {m.technique_name}
                </span>
                <span className="font-mono text-[9px] text-gray-400">{m.count}</span>
              </div>
            ))}
          </StatCard>
        )}

        {/* Top Hosts */}
        {data.top_hosts.length > 0 && (
          <StatCard>
            <CardLabel>Top Hosts</CardLabel>
            {data.top_hosts.map((h) => (
              <div key={h.host} className="flex justify-between items-center mb-1.5">
                <span className="font-mono text-[9px] text-gray-600 truncate">{h.host}</span>
                <span
                  className="font-mono text-[9px] font-bold"
                  style={{ color: SEV_HEX[h.highest_severity] }}
                >
                  {h.count}
                </span>
              </div>
            ))}
          </StatCard>
        )}
      </div>
    </div>
  );
}