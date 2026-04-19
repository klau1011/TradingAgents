import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Card } from "../components/ui/Card";
import { DecisionBadge, StatusBadge } from "../components/ui/StatusBadge";

export function HistoryPage() {
  const reports = useQuery({ queryKey: ["reports"], queryFn: api.listReports });
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: api.listRuns,
    refetchInterval: 5000,
  });

  return (
    <div className="mx-auto max-w-7xl px-32p py-80p space-y-80p">
      <header>
        <h1 className="font-display text-display-hero font-medium text-dark">
          History.
        </h1>
        <p className="text-body-lg text-slate-mid mt-3">
          Past analyses and currently active runs.
        </p>
      </header>

      <section className="space-y-6">
        <h2 className="font-display text-section font-medium">Active runs</h2>
        <Card>
          {runs.data && runs.data.length > 0 ? (
            <table className="w-full text-left">
              <thead>
                <tr className="text-slate-mid font-display text-body-em uppercase tracking-wider text-xs">
                  <th className="pb-4">Ticker</th>
                  <th className="pb-4">Date</th>
                  <th className="pb-4">Status</th>
                  <th className="pb-4">Decision</th>
                  <th className="pb-4">Started</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.run_id} className="border-t border-slate-tone">
                    <td className="py-3 font-display text-feature">
                      {r.ticker}
                    </td>
                    <td className="py-3 text-body">{r.analysis_date}</td>
                    <td className="py-3">
                      <StatusBadge status={r.status} kind="run" />
                    </td>
                    <td className="py-3">
                      {r.decision ? (
                        <DecisionBadge decision={r.decision} />
                      ) : (
                        <span className="text-slate-cool">—</span>
                      )}
                    </td>
                    <td className="py-3 text-slate-mid text-body">
                      {r.started_at?.slice(11, 19) ?? "—"}
                    </td>
                    <td className="py-3 text-right">
                      <Link
                        to={`/runs/${r.run_id}`}
                        className="font-display text-body-em text-rui-blue hover:opacity-85"
                      >
                        Open →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-slate-mid text-body">No active runs.</p>
          )}
        </Card>
      </section>

      <section className="space-y-6">
        <h2 className="font-display text-section font-medium">Saved reports</h2>
        <Card>
          {reports.isLoading ? (
            <p className="text-slate-mid text-body">Loading…</p>
          ) : reports.data && reports.data.length > 0 ? (
            <table className="w-full text-left">
              <thead>
                <tr className="text-slate-mid font-display text-body-em uppercase tracking-wider text-xs">
                  <th className="pb-4">Ticker</th>
                  <th className="pb-4">When</th>
                  <th className="pb-4">Decision</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {reports.data.map((r) => (
                  <tr key={r.folder} className="border-t border-slate-tone">
                    <td className="py-3 font-display text-feature">
                      {r.ticker}
                    </td>
                    <td className="py-3 text-body text-slate-mid">
                      {new Date(r.timestamp).toLocaleString()}
                    </td>
                    <td className="py-3">
                      {r.decision ? (
                        <DecisionBadge decision={r.decision} />
                      ) : (
                        <span className="text-slate-cool">—</span>
                      )}
                    </td>
                    <td className="py-3 text-right">
                      <Link
                        to={`/reports/${encodeURIComponent(r.folder)}`}
                        className="font-display text-body-em text-rui-blue hover:opacity-85"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-slate-mid text-body">No saved reports yet.</p>
          )}
        </Card>
      </section>
    </div>
  );
}
