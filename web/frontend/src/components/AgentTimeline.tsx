import { useEffect, useState } from "react";
import { Check, Circle, Loader2, AlertTriangle, Clock } from "lucide-react";
import type { AgentStatus } from "../types";
import type { AgentTimelineEntry } from "../hooks/useRunStream";

interface Props {
  agentOrder: string[];
  agents: Record<string, AgentStatus>;
  timeline: Record<string, AgentTimelineEntry>;
  runStartedAt: string | null;
  runFinishedAt: string | null;
}

/** Group key -> display label. Mirrors FIXED_AGENTS in tradingagents/runner.py. */
const GROUPS: { label: string; matcher: (agent: string) => boolean }[] = [
  {
    label: "Analysts",
    matcher: (a) =>
      /Market|Social|News|Fundamentals/.test(a) && /Analyst$/.test(a),
  },
  {
    label: "Research",
    matcher: (a) => /Bull Researcher|Bear Researcher|Research Manager/.test(a),
  },
  { label: "Trading", matcher: (a) => a === "Trader" },
  {
    label: "Risk",
    matcher: (a) =>
      /Aggressive Analyst|Neutral Analyst|Conservative Analyst/.test(a),
  },
  { label: "Portfolio", matcher: (a) => a === "Portfolio Manager" },
  { label: "Briefing", matcher: (a) => a === "Investor Briefing" },
];

function groupOf(agent: string): string {
  for (const g of GROUPS) {
    if (g.matcher(agent)) return g.label;
  }
  return "Other";
}

function StatusIcon({ status }: { status: AgentStatus | undefined }) {
  const cls = "shrink-0";
  switch (status) {
    case "in_progress":
      return (
        <Loader2
          size={14}
          className={`${cls} text-rui-blue motion-safe:animate-spin`}
        />
      );
    case "completed":
      return <Check size={14} className={`${cls} text-rui-teal`} />;
    case "error":
      return <AlertTriangle size={14} className={`${cls} text-rui-danger`} />;
    case "pending":
      return <Clock size={14} className={`${cls} text-muted`} />;
    default:
      return <Circle size={14} className={`${cls} text-subtle`} />;
  }
}

function fmtClock(iso: string | undefined | null): string {
  if (!iso) return "—";
  return iso.slice(11, 19);
}

function fmtDur(ms: number): string {
  if (ms < 0) return "0s";
  if (ms < 1000) return `${ms}ms`;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  return `${m}m ${rs}s`;
}

export function AgentTimeline({
  agentOrder,
  agents,
  timeline,
  runStartedAt,
  runFinishedAt,
}: Props) {
  // Tick once a second so the in-progress bars grow live.
  const [now, setNow] = useState(() => new Date().toISOString());
  useEffect(() => {
    if (runFinishedAt) return;
    const id = window.setInterval(
      () => setNow(new Date().toISOString()),
      1000
    );
    return () => window.clearInterval(id);
  }, [runFinishedAt]);

  if (agentOrder.length === 0) return null;

  const t0 = runStartedAt ? Date.parse(runStartedAt) : null;
  const t1Source = runFinishedAt ?? now;
  const t1 = Date.parse(t1Source);
  // Avoid division-by-zero and ensure a sensible minimum window so tiny bars
  // remain visible.
  const total = t0 != null ? Math.max(t1 - t0, 1000) : 1;

  // Group agents while preserving the runtime arrival order within each group.
  const grouped: Record<string, string[]> = {};
  for (const agent of agentOrder) {
    const g = groupOf(agent);
    (grouped[g] ??= []).push(agent);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <p className="font-display text-body-em text-inverse-fg/80">
          Agent timeline
        </p>
        <p className="font-display text-xs text-inverse-fg/60">
          {fmtClock(runStartedAt)} → {fmtClock(runFinishedAt ?? now)}
          {t0 != null && ` · ${fmtDur(total)}`}
        </p>
      </div>
      <div className="space-y-4">
        {GROUPS.filter((g) => grouped[g.label]?.length).map((group) => (
          <div key={group.label} className="space-y-2">
            <p className="font-display text-xs uppercase tracking-wider text-inverse-fg/50">
              {group.label}
            </p>
            <div className="space-y-1.5">
              {grouped[group.label].map((agent) => {
                const status = agents[agent];
                const tl = timeline[agent] ?? {};
                const startMs = tl.startedAt
                  ? Date.parse(tl.startedAt)
                  : null;
                const endMs = tl.completedAt
                  ? Date.parse(tl.completedAt)
                  : tl.erroredAt
                    ? Date.parse(tl.erroredAt)
                    : status === "in_progress"
                      ? t1
                      : null;
                const left =
                  t0 != null && startMs != null
                    ? ((startMs - t0) / total) * 100
                    : 0;
                const width =
                  t0 != null && startMs != null && endMs != null
                    ? Math.max(((endMs - startMs) / total) * 100, 1)
                    : 0;
                const barCls =
                  status === "completed"
                    ? "bg-rui-teal"
                    : status === "error"
                      ? "bg-rui-danger"
                      : status === "in_progress"
                        ? "bg-rui-blue motion-safe:animate-pulse"
                        : "bg-inverse-fg/20";
                const dur =
                  startMs != null && endMs != null
                    ? fmtDur(endMs - startMs)
                    : null;
                return (
                  <div
                    key={agent}
                    className="grid grid-cols-[160px_1fr_56px] items-center gap-3"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <StatusIcon status={status} />
                      <span
                        className="font-display text-body-em text-inverse-fg truncate"
                        title={agent}
                      >
                        {agent}
                      </span>
                    </div>
                    <div className="relative h-2 rounded-pill bg-inverse-fg/10 overflow-hidden">
                      {width > 0 && (
                        <div
                          className={`absolute top-0 bottom-0 ${barCls} rounded-pill`}
                          style={{
                            left: `${Math.min(left, 100)}%`,
                            width: `${Math.min(width, 100 - Math.min(left, 100))}%`,
                          }}
                        />
                      )}
                    </div>
                    <span className="font-display text-xs text-inverse-fg/60 text-right tabular-nums">
                      {dur ?? (status === "pending" ? "queued" : "—")}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
