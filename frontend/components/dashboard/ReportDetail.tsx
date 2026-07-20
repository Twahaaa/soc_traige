import type { TriageReport } from "@/types";
import { SEV_COLORS, SEV_HEX, cn } from "@/lib/utils";
import SeverityPill from "@/components/ui/SeverityPill";

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-gray-400 mb-1.5">
      {children}
    </div>
  );
}

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("bg-surface rounded-lg p-3", className)}>{children}</div>;
}

export default function ReportDetail({ report }: { report: TriageReport | null | undefined }) {
  if (!report) {
    return (
      <div className="flex-1 overflow-y-auto px-4 py-3 flex items-center justify-center text-gray-400 font-mono text-[11px]">
        Select an alert to view its triage report.
      </div>
    );
  }

  const c = SEV_COLORS[report.severity];
  const hex = SEV_HEX[report.severity];

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
      {/* Header */}
      <div className="flex gap-2.5 items-start">
        <SeverityPill severity={report.severity} />
        <div>
          <h2 className="text-[13px] font-bold leading-snug" data-testid="report-title">
            {report.title} — {report.affected_host}
          </h2>
          <div className="flex gap-2 mt-1 flex-wrap">
            {[
              report.incident_id,
              `Host: ${report.affected_host}`,
              `Source: ${report.log_source}`,
              `Detection: ${report.detection_source}`,
              new Date(report.timestamp).toISOString().replace("T", " ").slice(0, 19) + " UTC",
            ].map((m) => (
              <span key={m} className="font-mono text-[9px] text-gray-400">
                {m}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Anomaly Score */}
      <div>
        <SectionLabel>Anomaly Score (NeuralLog Confidence)</SectionLabel>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1 bg-surface rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${Math.min(100, Math.max(0, report.anomaly_score * 100))}%`, background: hex }}
            />
          </div>
          <span className="font-mono text-[11px] font-bold" style={{ color: hex }}>
            {report.anomaly_score.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Description */}
      <div>
        <SectionLabel>Description</SectionLabel>
        <p className="text-[11px] leading-relaxed text-gray-600">{report.description}</p>
      </div>

      {/* Evidence */}
      <div>
        <SectionLabel>Evidence Log Lines</SectionLabel>
        <div className={cn("rounded-lg border-l-2 p-2.5 bg-surface", c.border)}>
          {report.evidence.map((line, i) => {
            const [ts, ...rest] = line.split(" ");
            const msg = rest.join(" ");
            return (
              <div key={i} className="flex gap-2 font-mono text-[10px] leading-relaxed">
                <span className="text-gray-400 flex-shrink-0">{ts}</span>
                <span
                  dangerouslySetInnerHTML={{
                    __html: msg.replace(
                      /(root|FAILED|failure|bash|webshell|\d+\.\d+\.\d+\.\d+)/g,
                      `<em style="color:${hex};font-style:normal;font-weight:600">$1</em>`,
                    ),
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* MITRE */}
      {report.mitre_attack && (
        <div>
          <SectionLabel>MITRE ATT&amp;CK Mapping</SectionLabel>
          <Card className="flex gap-3 items-center">
            <span className="font-mono text-[10px] font-bold px-2 py-1 rounded bg-info-bg text-info-text flex-shrink-0">
              {report.mitre_attack.technique_id}
            </span>
            <div>
              <div className="text-[11px] font-semibold">{report.mitre_attack.technique_name}</div>
              <div className="font-mono text-[9px] text-gray-400 mt-0.5">
                Tactic: {report.mitre_attack.tactic}
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* IP Reputation */}
      {report.ip_reputation && (
        <div>
          <SectionLabel>IP Reputation — {report.ip_reputation.ip}</SectionLabel>
          <div className="grid grid-cols-2 gap-2 bg-surface rounded-lg p-3">
            {[
              {
                label: "Abuse Score",
                value: `${report.ip_reputation.abuse_score} / 100`,
                danger: report.ip_reputation.abuse_score > 70,
              },
              { label: "Country", value: report.ip_reputation.country },
              { label: "ISP / Type", value: report.ip_reputation.isp },
              {
                label: "Total Reports",
                value: report.ip_reputation.total_reports.toLocaleString(),
              },
            ].map((f) => (
              <div key={f.label}>
                <div className="font-mono text-[8px] uppercase tracking-wider text-gray-400 mb-0.5">
                  {f.label}
                </div>
                <div
                  className={cn(
                    "font-mono text-[11px] font-semibold",
                    f.danger ? "text-critical" : "text-gray-800",
                  )}
                >
                  {f.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CVE */}
      {report.cve_references.length > 0 && (
        <div>
          <SectionLabel>CVE References</SectionLabel>
          <div className="flex gap-1.5 flex-wrap">
            {report.cve_references.map((c4) => (
              <span
                key={c4}
                className="font-mono text-[10px] px-2 py-0.5 rounded bg-critical-bg text-critical-text"
              >
                {c4}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Remediation */}
      <div>
        <SectionLabel>Remediation Steps</SectionLabel>
        <div className="flex flex-col gap-1.5">
          {report.remediation_steps.map((step, i) => (
            <div key={i} className="flex gap-2 items-start">
              <div className="w-5 h-5 rounded flex items-center justify-center bg-surface font-mono text-[9px] font-bold text-gray-400 flex-shrink-0 mt-0.5">
                {i + 1}
              </div>
              <p className="text-[11px] leading-relaxed text-gray-600">{step}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Similar */}
      {report.similar_past_incidents.length > 0 && (
        <div>
          <SectionLabel>Similar Past Incidents (via Qdrant vector search)</SectionLabel>
          <div className="flex gap-1.5 flex-wrap">
            {report.similar_past_incidents.map((id) => (
              <span
                key={id}
                className="font-mono text-[10px] px-2 py-0.5 rounded bg-info-bg text-info-text"
              >
                {id}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}