import type { AgentStatus, RunStatus } from "../../types";

const agentColor: Record<AgentStatus, string> = {
  pending: "bg-subtle/20 text-muted",
  in_progress: "bg-rui-blue/15 text-rui-blue",
  completed: "bg-rui-teal/15 text-rui-teal",
  error: "bg-rui-danger/15 text-rui-danger",
};

const runColor: Record<RunStatus, string> = {
  queued: "bg-rui-yellow/15 text-rui-yellow",
  running: "bg-rui-blue/15 text-rui-blue",
  done: "bg-rui-teal/15 text-rui-teal",
  error: "bg-rui-danger/15 text-rui-danger",
  cancelled: "bg-subtle/20 text-muted",
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
      className={`inline-flex items-center gap-2 rounded-pill px-3 py-1 text-body-em font-display ${cls}`}
    >
      <Dot status={status} />
      {label ?? status.replace("_", " ")}
    </span>
  );
}

function Dot({ status }: { status: string }) {
  const color =
    status === "in_progress" || status === "running"
      ? "bg-rui-blue"
      : status === "completed" || status === "done"
        ? "bg-rui-teal"
        : status === "error"
          ? "bg-rui-danger"
          : status === "queued"
            ? "bg-rui-yellow"
            : status === "cancelled"
              ? "bg-subtle"
              : "bg-subtle";
  const animate =
    status === "in_progress" || status === "running"
      ? "motion-safe:animate-pulse"
      : "";
  return <span className={`h-2 w-2 rounded-pill ${color} ${animate}`} />;
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
    ? "bg-rui-teal text-white"
    : isSell && !isBuy
      ? "bg-rui-danger text-white"
      : isHold
        ? "bg-rui-yellow text-white"
        : "bg-subtle text-white";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-pill px-32p py-14p font-display text-nav font-medium ${cls} ${
        preview ? "opacity-80" : ""
      }`}
    >
      {preview && (
        <span className="text-xs uppercase tracking-wider opacity-80">
          Preview
        </span>
      )}
      {upper}
    </span>
  );
}
