import { useQuery } from "@tanstack/react-query";
import { Target } from "lucide-react";
import { api } from "../api";
import { Card } from "../components/ui/Card";
import { DecisionBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonTable } from "../components/ui/Skeleton";
import type { TrackRecordStats, TrackRecordTicker } from "../types";

const pct = (v: number | null, digits = 0) =>
  v === null ? "—" : `${(v * 100).toFixed(digits)}%`;

/** Alpha arrives pre-formatted from the log ("+3.2%"); colour by its sign. */
function AlphaCell({ alpha }: { alpha: string | null }) {
  if (!alpha) return <span className="text-muted">—</span>;
  const negative = alpha.trim().startsWith("-");
  return (
    <span className={negative ? "text-rui-danger" : "text-rui-teal"}>
      {alpha}
    </span>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="font-display text-nav text-muted">{label}</p>
      <p className="font-display text-display-sm font-medium">{value}</p>
      {hint && <p className="text-body-em text-muted">{hint}</p>}
    </div>
  );
}

function Overall({ stats }: { stats: TrackRecordStats }) {
  return (
    <Card className="grid grid-cols-2 md:grid-cols-4 gap-32p">
      <Stat
        label="Hit rate"
        value={pct(stats.hit_rate)}
        hint={`${stats.hits}/${stats.scored} directional calls`}
      />
      <Stat label="Avg alpha" value={pct(stats.avg_alpha, 1)} hint="vs benchmark" />
      <Stat label="Decisions" value={String(stats.total)} />
      <Stat
        label="Awaiting outcome"
        value={String(stats.pending)}
        hint="resolve at the full holding window"
      />
    </Card>
  );
}

function TickerCard({ t }: { t: TrackRecordTicker }) {
  return (
    <Card className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 className="font-display text-display-sm font-medium">{t.ticker}</h2>
        <p className="text-body-em text-muted">
          {t.scored > 0
            ? `${pct(t.hit_rate)} hit rate · ${t.hits}/${t.scored} scored`
            : "no scored calls yet"}
          {t.pending > 0 && ` · ${t.pending} pending`}
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="font-display text-nav text-muted">
              <th className="py-2 pr-6">Date</th>
              <th className="py-2 pr-6">Rating</th>
              <th className="py-2 pr-6">Return</th>
              <th className="py-2 pr-6">Alpha</th>
              <th className="py-2">Held</th>
            </tr>
          </thead>
          <tbody>
            {t.entries.map((e) => (
              <tr key={`${e.date}-${e.rating}`} className="border-t border-edge">
                <td className="py-3 pr-6 whitespace-nowrap">{e.date}</td>
                <td className="py-3 pr-6">
                  <DecisionBadge decision={e.rating} preview />
                </td>
                <td className="py-3 pr-6">
                  {e.pending ? (
                    <span className="text-muted">pending</span>
                  ) : (
                    e.raw ?? "—"
                  )}
                </td>
                <td className="py-3 pr-6">
                  {e.pending ? <span className="text-muted">—</span> : <AlphaCell alpha={e.alpha} />}
                </td>
                <td className="py-3 text-muted">{e.holding ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function TrackRecordPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["track-record"],
    queryFn: api.getTrackRecord,
  });

  return (
    <div className="mx-auto max-w-5xl px-32p py-80p space-y-32p">
      <header className="space-y-6">
        <h1 className="font-display text-display-hero font-medium">
          Track record.
        </h1>
        <p className="text-body-lg text-muted max-w-2xl">
          Every past decision scored against its realized alpha. Hold calls take
          no position, so they are excluded from the hit rate rather than
          counted as misses.
        </p>
      </header>

      {isLoading && <SkeletonTable />}

      {data && data.overall.total === 0 && (
        <EmptyState
          icon={Target}
          title="No decisions logged yet"
          description="Run an analysis — each decision is recorded and scored once its holding window closes."
        />
      )}

      {data && data.overall.total > 0 && (
        <>
          <Overall stats={data.overall} />
          {data.tickers.map((t) => (
            <TickerCard key={t.ticker} t={t} />
          ))}
        </>
      )}
    </div>
  );
}
