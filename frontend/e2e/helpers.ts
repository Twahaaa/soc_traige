import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

import type { TriageReport } from "@/types";

/**
 * Push a TriageReport into the dashboard's live stream by XADDing it to
 * stream:triage_reports in Redis. The FastAPI WebSocket bridge, which belongs
 * to consumer group group:dashboard, picks it up and forwards it to all
 * connected dashboard clients.
 *
 * Returns the constructed report (so the test can assert the rendered fields).
 */
export function pushLiveReport(overrides: Partial<TriageReport> = {}): TriageReport {
  const report: TriageReport = {
    incident_id: randomUUID(),
    timestamp: new Date().toISOString(),
    severity: "High",
    title: `E2E live WS @ ${new Date().toISOString().slice(11, 19)}`,
    affected_host: "e2e-host",
    log_source: "synthetic",
    anomaly_score: 0.8125,
    description: "Synthetic live-streamed report pushed by the Playwright E2E suite.",
    evidence: [
      "Jan 30 14:35:01 e2e-host sshd[2103]: Failed password for invalid user tom from 203.0.113.5",
    ],
    cve_references: [],
    ip_reputation: {
      ip: "203.0.113.5",
      abuse_score: 73,
      country: "RU",
      isp: "Example ISP",
      total_reports: 412,
    },
    mitre_attack: {
      technique_id: "T1110",
      technique_name: "Brute Force",
      tactic: "Credential Access",
      description: "Adversary attempts many passwords against authentication.",
    },
    remediation_steps: ["Block source IP at the firewall."],
    similar_past_incidents: [],
    detection_source: "prefilter",
    ...overrides,
  };

  execFileSync("redis-cli", [
    "XADD",
    "stream:triage_reports",
    "*",
    "report",
    JSON.stringify(report),
  ]);

  return report;
}