// Wire contract — mirrors backend TriageReport (snake_case) verbatim.
// Source of truth: backend/triage/report_schema.py + backend/dashboard/schemas.py.
// Do NOT rename to camelCase; the FastAPI response is already snake_case.

export type Severity = "Critical" | "High" | "Medium" | "Low" | "Informational";

export interface IPReputation {
  ip: string;
  abuse_score: number;
  country: string;
  isp: string;
  total_reports: number;
}

export interface MitreAttack {
  technique_id: string;
  technique_name: string;
  tactic: string;
  description: string;
}

export interface TriageReport {
  incident_id: string;
  timestamp: string;
  severity: Severity;
  title: string;
  affected_host: string;
  log_source: string;
  anomaly_score: number;
  description: string;
  evidence: string[];
  cve_references: string[];
  ip_reputation: IPReputation | null;
  mitre_attack: MitreAttack | null;
  remediation_steps: string[];
  similar_past_incidents: string[];
  detection_source: string;
}

export interface MitreCount {
  technique_id: string;
  technique_name: string;
  count: number;
}

export interface HostStat {
  host: string;
  count: number;
  highest_severity: Severity;
  last_seen: string;
}

export interface TimelineEvent {
  incident_id: string;
  timestamp: string;
  severity: Severity;
  title: string;
  host: string;
  anomaly_score: number;
}

export type ComponentStatus = "ok" | "warn" | "error";

export interface SystemStatus {
  name: string;
  status: ComponentStatus;
  detail: string;
}

export interface Health {
  components: SystemStatus[];
}

export interface Stats {
  total_alerts_24h: number;
  total_alerts_all: number;
  severity_distribution: Record<Severity, number>;
  top_mitre: MitreCount[];
  top_hosts: HostStat[];
}

// Envelope returned by GET /api/reports
export interface ReportList {
  items: TriageReport[];
  total: number;
  limit: number;
  offset: number;
}