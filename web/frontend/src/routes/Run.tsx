import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useMutation } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  History as HistoryIcon,
  MessageSquare,
  PlusCircle,
  Square,
  Wrench,
} from "lucide-react";

import { api } from "../api";
import { useRunStream } from "../hooks/useRunStream";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import {
  DecisionBadge,
  StatusBadge,
} from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonText } from "../components/ui/Skeleton";
import { AgentTimeline } from "../components/AgentTimeline";
import { previewDecision } from "../utils/decision";
import { SECTION_LABELS } from "../types";

export function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const state = useRunStream(runId);

  const reportEntries = Object.entries(state.reports);
  const latestReport = reportEntries[reportEntries.length - 1];

  const cancellable =
    state.status === "queued" || state.status === "running";

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelRun(runId!),
  });

  // Live preview of the Portfolio Manager's decision while the section streams.
  const liveDecision = useMemo(
    () => previewDecision(state.reports["final_trade_decision"]),
    [state.reports]
  );

  return (
    <div className="space-y-0">
      {/* Inverted hero section: status + decision callout */}
      <section className="bg-inverse text-inverse-fg px-32p py-80p">
        <div className="mx-auto max-w-7xl space-y-32p">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-3">
              <p className="font-display text-nav text-inverse-fg/60">
                Run {runId?.slice(0, 8)}
              </p>
              <h1 className="font-display text-display-hero font-medium">
                {state.decision ? (
                  <DecisionBadge decision={state.decision} />
                ) : (
                  <span className="text-inverse-fg">
                    {state.status === "queued"
                      ? `Queued · position ${(state.queuePosition ?? 0) + 1}`
                      : state.status === "running"
                        ? "Analyzing…"
                        : state.status === "error"
                          ? "Errored"
                          : state.status === "cancelled"
                            ? "Cancelled"
                            : "Done"}
                  </span>
                )}
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={state.status} kind="run" />
              {cancellable && (
                <Button
                  variant="danger"
                  type="button"
                  disabled={
                    cancelMutation.isPending || cancelMutation.isSuccess
                  }
                  onClick={() => {
                    if (
                      window.confirm(
                        "Cancel this run? In-flight LLM calls will finish before the run stops."
                      )
                    ) {
                      cancelMutation.mutate();
                    }
                  }}
                  title="Cancel run"
                >
                  <Square size={16} aria-hidden="true" />
                  {cancelMutation.isPending
                    ? "Cancelling…"
                    : cancelMutation.isSuccess
                      ? "Cancelling…"
                      : "Cancel run"}
                </Button>
              )}
            </div>
          </div>

          {/* Live decision preview — shown while still running. */}
          {!state.decision && liveDecision && (
            <div className="flex items-center gap-3">
              <span className="font-display text-xs uppercase tracking-wider text-inverse-fg/60">
                Tentative
              </span>
              <DecisionBadge decision={liveDecision} preview />
            </div>
          )}

          {/* Agent timeline — replaces the static status pill grid. */}
          {state.agentOrder.length > 0 ? (
            <AgentTimeline
              agentOrder={state.agentOrder}
              agents={state.agents}
              timeline={state.agentTimeline}
              runStartedAt={state.runStartedAt}
              runFinishedAt={state.runFinishedAt}
            />
          ) : state.backfilling ? (
            <SkeletonText lines={6} className="opacity-30" />
          ) : null}

          {state.reconnecting && (
            <Card className="bg-rui-yellow/10 text-rui-yellow border-rui-yellow/30">
              <p className="font-display text-body-em">Connection interrupted. Reconnecting…</p>
              {state.lastError && (
                <p className="mt-2 text-body">{state.lastError}</p>
              )}
            </Card>
          )}

          {state.error && (
            <Card className="bg-rui-danger text-white border-0">
              <p className="font-display text-feature font-medium mb-2">Error</p>
              <pre className="whitespace-pre-wrap text-body">{state.error}</pre>
            </Card>
          )}

          {cancelMutation.isError && (
            <Card className="bg-rui-danger/10 text-rui-danger border-rui-danger/30">
              <p className="font-display text-body-em">
                Could not cancel: {String(cancelMutation.error)}
              </p>
            </Card>
          )}

          <div className="flex flex-wrap gap-4">
            <Link to="/">
              <Button variant="ghost">
                <PlusCircle size={16} aria-hidden="true" />
                New run
              </Button>
            </Link>
            <Link to="/history">
              <Button variant="ghost">
                <HistoryIcon size={16} aria-hidden="true" />
                History
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Alternating elevated surface: streaming report + activity feed */}
      <section className="bg-surface px-32p py-80p">
        <div className="mx-auto max-w-7xl grid grid-cols-1 lg:grid-cols-3 gap-32p">
          <Card className="lg:col-span-2 max-h-[80vh] overflow-y-auto">
            <h2 className="font-display text-card font-medium mb-4">
              {latestReport
                ? SECTION_LABELS[latestReport[0]] ?? latestReport[0]
                : state.backfilling
                  ? "Loading report…"
                  : "Awaiting first report"}
            </h2>
            {latestReport ? (
              <article className="md-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {latestReport[1]}
                </ReactMarkdown>
              </article>
            ) : state.backfilling ? (
              <SkeletonText lines={6} />
            ) : (
              <EmptyState
                title="No report yet"
                description="Reports will stream in here as each agent finishes its section."
              />
            )}

            {reportEntries.length > 1 && (
              <details className="mt-32p">
                <summary className="font-display text-body-em cursor-pointer text-muted">
                  Other sections ({reportEntries.length - 1})
                </summary>
                <div className="mt-4 space-y-32p">
                  {reportEntries.slice(0, -1).map(([key, content]) => (
                    <div key={key}>
                      <h3 className="font-display text-feature font-medium mb-2">
                        {SECTION_LABELS[key] ?? key}
                      </h3>
                      <article className="md-body">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {content}
                        </ReactMarkdown>
                      </article>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </Card>

          <ActivityFeed
            backfilling={state.backfilling}
            messages={state.messages}
            toolCalls={state.toolCalls}
          />
        </div>
      </section>

      {state.status === "done" && state.reportPath && (
        <section className="bg-canvas px-32p py-80p">
          <div className="mx-auto max-w-7xl flex flex-wrap items-center justify-between gap-4">
            <p className="font-display text-feature text-muted">
              Report saved to <code className="text-fg">{state.reportPath}</code>
            </p>
            <Link to="/history">
              <Button variant="primary">
                Open in history
                <ArrowRight size={16} aria-hidden="true" />
              </Button>
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}

function ActivityFeed({
  backfilling,
  messages,
  toolCalls,
}: {
  backfilling: boolean;
  messages: { ts: string; type: string; content: string }[];
  toolCalls: { ts: string; name: string; args: Record<string, unknown> }[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [messages.length, toolCalls.length]);

  type Item = { ts: string; kind: string; text: string };
  const items: Item[] = [
    ...messages.map((m) => ({ ts: m.ts, kind: m.type, text: m.content })),
    ...toolCalls.map((t) => ({
      ts: t.ts,
      kind: "Tool",
      text: `${t.name}(${Object.entries(t.args)
        .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
        .join(", ")})`,
    })),
  ].sort((a, b) => a.ts.localeCompare(b.ts));

  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  return (
    <Card className="max-h-[80vh] overflow-hidden flex flex-col">
      <h2 className="font-display text-card font-medium mb-4">Activity</h2>
      <div ref={ref} className="flex-1 overflow-y-auto space-y-3 pr-2">
        {items.map((it, idx) => {
          const isLong = it.text.length > 280;
          const isOpen = !!expanded[idx];
          const text = isLong && !isOpen ? it.text.slice(0, 280) + "…" : it.text;
          const Icon = kindIcon(it.kind);
          return (
            <div key={idx} className="border-b border-edge/60 pb-2 last:border-0">
              <div className="flex items-center gap-2 mb-1">
                <Icon size={12} className="text-muted" aria-hidden="true" />
                <span className="font-display text-xs text-subtle">
                  {it.ts.slice(11, 19)}
                </span>
                <span className="font-display text-xs uppercase tracking-wider text-muted">
                  {it.kind}
                </span>
              </div>
              <p className="text-body-em text-fg break-words">{text}</p>
              {isLong && (
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((s) => ({ ...s, [idx]: !s[idx] }))
                  }
                  className="mt-1 font-display text-xs text-rui-blue hover:opacity-85"
                >
                  {isOpen ? "Show less" : "Show more"}
                </button>
              )}
            </div>
          );
        })}
        {items.length === 0 &&
          (backfilling ? (
            <SkeletonText lines={6} />
          ) : (
            <EmptyState
              icon={Activity}
              title="Waiting for events"
              description="The agent stream will appear here as soon as the run starts."
            />
          ))}
      </div>
    </Card>
  );
}

function kindIcon(kind: string) {
  if (kind === "Tool") return Wrench;
  if (kind === "System" || kind === "Control") return AlertTriangle;
  return MessageSquare;
}
