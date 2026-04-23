import type {
  ConfigOptions,
  ReportDetail,
  ReportSummary,
  RunDetail,
  RunSummary,
} from "./types";

const json = async <T,>(res: Response): Promise<T> => {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
};

export const api = {
  options: () => fetch("/api/config/options").then(json<ConfigOptions>),
  startRun: (body: Record<string, unknown>) =>
    fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<RunSummary>),
  listRuns: () =>
    fetch("/api/runs").then(json<{ runs: RunSummary[] }>).then((r) => r.runs),
  getRun: (id: string) => fetch(`/api/runs/${id}`).then(json<RunDetail>),
  cancelRun: (id: string) =>
    fetch(`/api/runs/${id}`, { method: "DELETE" }).then(
      json<{ run_id: string; status: string }>
    ),
  listReports: () =>
    fetch("/api/reports")
      .then(json<{ reports: ReportSummary[] }>)
      .then((r) => r.reports),
  getReport: (folder: string) =>
    fetch(`/api/reports/${encodeURIComponent(folder)}`).then(json<ReportDetail>),
};

export function streamUrl(runId: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/runs/${runId}/stream`;
}
