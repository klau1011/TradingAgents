import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, FileText, ArrowRight } from "lucide-react";
import { api } from "../api";
import { Card } from "../components/ui/Card";
import { DecisionBadge, StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonTable } from "../components/ui/Skeleton";

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
        <h1 className="font-display text-display-hero font-medium text-fg">
          History.
        </h1>
        <p className="text-body-lg text-muted mt-3">
          Past analyses and currently active runs.
        </p>
      </header>

      <section className="space-y-6">
        <h2 className="font-display text-section font-medium">Active runs</h2>
        <Card>
          {runs.isLoading ? (
            <SkeletonTable rows={3} cols={6} />
          ) : runs.data && runs.data.length > 0 ? (
            <table className="w-full text-left">
              <thead>
                <tr className="text-muted font-display text-body-em uppercase tracking-wider text-xs">
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
                  <tr key={r.run_id} className="border-t border-edge">
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
                        <span className="text-subtle">—</span>
                      )}
                    </td>
                    <td className="py-3 text-muted text-body">
                      {r.started_at?.slice(11, 19) ?? "—"}
                    </td>
                    <td className="py-3 text-right">
                      <Link
                        to={`/runs/${r.run_id}`}
                        className="inline-flex items-center gap-1 font-display text-body-em text-rui-blue hover:opacity-85"
                      >
                        Open <ArrowRight size={14} aria-hidden="true" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              icon={Activity}
              title="No active runs"
              description="Start a new analysis from the New Run page to see live progress here."
            />
          )}
        </Card>
      </section>

      <section className="space-y-6">
        <h2 className="font-display text-section font-medium">Saved reports</h2>
        <Card>
          {reports.isLoading ? (
            <SkeletonTable rows={5} cols={4} />
          ) : reports.data && reports.data.length > 0 ? (
            <table className="w-full text-left">
              <thead>
                <tr className="text-muted font-display text-body-em uppercase tracking-wider text-xs">
                  <th className="pb-4">Ticker</th>
                  <th className="pb-4">When</th>
                  <th className="pb-4">Decision</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {reports.data.map((r) => (
                  <tr key={r.folder} className="border-t border-edge">
                    <td className="py-3 font-display text-feature">
                      {r.ticker}
                    </td>
                    <td className="py-3 text-body text-muted">
                      {new Date(r.timestamp).toLocaleString()}
                    </td>
                    <td className="py-3">
                      {r.decision ? (
                        <DecisionBadge decision={r.decision} />
                      ) : (
                        <span className="text-subtle">—</span>
                      )}
                    </td>
                    <td className="py-3 text-right">
                      <Link
                        to={`/reports/${encodeURIComponent(r.folder)}`}
                        className="inline-flex items-center gap-1 font-display text-body-em text-rui-blue hover:opacity-85"
                      >
                        View <ArrowRight size={14} aria-hidden="true" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              icon={FileText}
              title="No saved reports yet"
              description="Completed analyses are written to disk and will appear here."
            />
          )}
        </Card>
      </section>
    </div>
  );
}
