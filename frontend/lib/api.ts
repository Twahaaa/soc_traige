"use client";

import useSWR, { type KeyedMutator } from "swr";
import type {
  Health,
  HostStat,
  ReportList,
  Stats,
  TriageReport,
} from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${body}`.trim());
  }
  return (await res.json()) as T;
}

export { API_BASE };

// Append/prepend helpers operate on the ReportList envelope kept in SWR cache.
function reportListEnvelop(items: TriageReport[]): ReportList {
  return { items, total: items.length, limit: 100, offset: 0 };
}

export function useReports(
  severity: string | undefined,
): {
  data?: TriageReport[];
  isLoading: boolean;
  error?: Error;
  mutate: KeyedMutator<ReportList>;
} {
  const qs = new URLSearchParams();
  qs.set("limit", "100");
  if (severity && severity !== "All") qs.set("severity", severity);
  const { data, error, isLoading, mutate } = useSWR<ReportList>(
    `/api/reports?${qs.toString()}`,
    fetcher<ReportList>,
    { refreshInterval: 15000, keepPreviousData: true },
  );
  return { data: data?.items, isLoading, error, mutate };
}

// Helper for the dashboard page to merge a streamed report into the cache.
export function prependReport(prev: ReportList | undefined, report: TriageReport): ReportList {
  const items = prev?.items ?? [];
  if (items.some((r) => r.incident_id === report.incident_id)) return prev ?? reportListEnvelop(items);
  const merged = [report, ...items].sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1));
  return reportListEnvelop(merged);
}

export function mergeSnapshot(prev: ReportList | undefined, snapshot: TriageReport[]): ReportList {
  const items = prev?.items ?? [];
  const seen = new Set(items.map((r) => r.incident_id));
  const merged = [...snapshot.filter((r) => !seen.has(r.incident_id)), ...items].sort((a, b) =>
    a.timestamp < b.timestamp ? 1 : -1,
  );
  return reportListEnvelop(merged);
}

export function useReport(
  incidentId: string | null,
): { data?: TriageReport; isLoading: boolean; error?: Error } {
  const { data, error, isLoading } = useSWR<TriageReport>(
    incidentId ? `/api/reports/${encodeURIComponent(incidentId)}` : null,
    fetcher<TriageReport>,
  );
  return { data, isLoading, error };
}

export function useStats(): { data?: Stats; isLoading: boolean; error?: Error } {
  const { data, error, isLoading } = useSWR<Stats>("/api/stats", fetcher<Stats>, {
    refreshInterval: 15000,
  });
  return { data, isLoading, error };
}

export function useHosts(): { data?: HostStat[]; isLoading: boolean; error?: Error } {
  const { data, error, isLoading } = useSWR<HostStat[]>("/api/hosts", fetcher<HostStat[]>, {
    refreshInterval: 30000,
  });
  return { data, isLoading, error };
}

export function useHealth(): { data?: Health; isLoading: boolean; error?: Error } {
  const { data, error, isLoading } = useSWR<Health>("/api/health", fetcher<Health>, {
    refreshInterval: 10000,
  });
  return { data, isLoading, error };
}

// WS API base — derives ws(s):// from NEXT_PUBLIC_API_URL, default ws://localhost:8000.
function wsBaseUrl(): string {
  const base = API_BASE;
  if (base.startsWith("https")) return `wss${base.slice(5)}`;
  if (base.startsWith("http")) return `ws${base.slice(4)}`;
  return "ws://localhost:8000";
}

export interface ReportStreamHandlers {
  onSnapshot: (reports: TriageReport[]) => void;
  onReport: (report: TriageReport) => void;
  onError?: (err: Event) => void;
}

/**
 * Open the /ws/reports stream. Returns a cleanup function.
 * On connect: server sends {"type":"snapshot","items":[...]} — handlers.onSnapshot.
 * On live push: {"type":"report","item":{...}} — handlers.onReport.
 */
export function connectReportStream(handlers: ReportStreamHandlers): () => void {
  const url = `${wsBaseUrl()}/ws/reports`;
  let closed = false;
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let retryDelayMs = 1000;

  const open = () => {
    if (closed) return;
    try {
      socket = new WebSocket(url);
    } catch (err) {
      handlers.onError?.(err as Event);
      scheduleRetry();
      return;
    }
    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "snapshot" && Array.isArray(msg.items)) {
          handlers.onSnapshot(msg.items as TriageReport[]);
        } else if (msg.type === "report" && msg.item) {
          handlers.onReport(msg.item as TriageReport);
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    socket.onerror = (err) => {
      handlers.onError?.(err);
    };
    socket.onclose = () => {
      socket = null;
      scheduleRetry();
    };
    socket.onopen = () => {
      retryDelayMs = 1000;
    };
  };

  const scheduleRetry = () => {
    if (closed) return;
    if (retry) clearTimeout(retry);
    retry = setTimeout(open, retryDelayMs);
    retryDelayMs = Math.min(retryDelayMs * 2, 15000);
  };

  open();

  return () => {
    closed = true;
    if (retry) clearTimeout(retry);
    if (socket) {
      socket.onclose = null;
      socket.onmessage = null;
      socket.onerror = null;
      try { socket.close(); } catch { /* noop */ }
    }
  };
}