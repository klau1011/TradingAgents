import type { AgentStatus, RunStatus } from "../../types";

const agentColor: Record<AgentStatus, string> = {
  pending: "text-muted",
  in_progress: "bg-accent-soft text-accent",
  completed: "bg-ok-soft text-ok",
  error: "bg-bad-soft text-bad",
};

const runColor: Record<RunStatus, string> = {
  queued: "text-muted",
  running: "bg-accent-soft text-accent",
  done: "bg-ok-soft text-ok",
  error: "bg-bad-soft text-bad",
  cancelled: "text-muted",
};

export function StatusBadge({
  status,
  kind = "agent",
  label,
}: {
  status: string;
  kind?: "agent" | "run";
  label?: string;
}) {
  const map = kind === "run" ? runColor : agentColor;
  const cls = (map as Record<string, string>)[status] ?? agentColor.pending;
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-chip border border-edge px-3 py-1 text-body-em font-display font-medium ${cls}`}
    >
      {label ?? status.replace("_", " ")}
    </span>
  );
}

export function DecisionBadge({
  decision,
  preview = false,
}: {
  decision: string | null;
  preview?: boolean;
}) {
  if (!decision) return null;
  const upper = decision.toUpperCase();
  const isBuy = /\b(BUY|OVERWEIGHT)\b/.test(upper);
  const isSell = /\b(SELL|UNDERWEIGHT)\b/.test(upper);
  const isHold = /\bHOLD\b/.test(upper);
  const cls = isBuy && !isSell
    ? "bg-ok-soft text-ok"
    : isSell && !isBuy
      ? "bg-bad-soft text-bad"
      : isHold
        ? "bg-surface text-fg"
        : "bg-surface text-muted";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-pill border border-edge-strong px-4 py-2 font-display text-nav font-medium ${cls}`}
    >
      {preview && <span className="text-xs text-muted">Preview</span>}
      {upper}
    </span>
  );
}
