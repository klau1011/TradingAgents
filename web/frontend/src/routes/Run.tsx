import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useRunStream } from "../hooks/useRunStream";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import {
  DecisionBadge,
  StatusBadge,
} from "../components/ui/StatusBadge";
import { SECTION_LABELS } from "../types";

export function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const state = useRunStream(runId);

  const reportEntries = Object.entries(state.reports);
  const latestReport = reportEntries[reportEntries.length - 1];

  return (
    <div className="space-y-0">
      {/* Dark header section: status + decision callout */}
      <section className="bg-dark text-white px-32p py-80p">
        <div className="mx-auto max-w-7xl space-y-32p">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-3">
              <p className="font-display text-nav text-slate-cool">
                Run {runId?.slice(0, 8)}
              </p>
              <h1 className="font-display text-display-hero font-medium">
                {state.decision ? (
                  <DecisionBadge decision={state.decision} />
                ) : (
                  <span className="text-white">
                    {state.status === "queued"
                      ? `Queued · position ${(state.queuePosition ?? 0) + 1}`
                      : state.status === "running"
                        ? "Analyzing…"
                        : state.status === "error"
                          ? "Errored"
                          : "Done"}
                  </span>
                )}
              </h1>
            </div>
            <StatusBadge status={state.status} kind="run" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {state.agentOrder.map((agent) => (
              <div
                key={agent}
                className="flex items-center justify-between rounded-card bg-white/5 px-4 py-3 border border-white/10"
              >
                <span className="font-display text-body-em">{agent}</span>
                <StatusBadge status={state.agents[agent]} />
              </div>
            ))}
          </div>

          {state.error && (
            <Card className="bg-rui-danger text-white border-0">
              <p className="font-display text-feature font-medium mb-2">Error</p>
              <pre className="whitespace-pre-wrap text-body">{state.error}</pre>
            </Card>
          )}

          <div className="flex gap-4">
            <Link to="/">
              <Button variant="ghost">New run</Button>
            </Link>
            <Link to="/history">
              <Button variant="ghost">History</Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Light section: streaming report + activity feed */}
      <section className="bg-surface px-32p py-80p">
        <div className="mx-auto max-w-7xl grid grid-cols-1 lg:grid-cols-3 gap-32p">
          <Card className="lg:col-span-2 max-h-[80vh] overflow-y-auto">
            <h2 className="font-display text-card font-medium mb-4">
              {latestReport
                ? SECTION_LABELS[latestReport[0]] ?? latestReport[0]
                : "Awaiting first report…"}
            </h2>
            {latestReport ? (
              <article className="md-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {latestReport[1]}
                </ReactMarkdown>
              </article>
            ) : (
              <p className="text-slate-mid text-body">
                Reports will stream in as each agent finishes.
              </p>
            )}

            {reportEntries.length > 1 && (
              <details className="mt-32p">
                <summary className="font-display text-body-em cursor-pointer text-slate-mid">
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
            messages={state.messages}
            toolCalls={state.toolCalls}
          />
        </div>
      </section>

      {state.status === "done" && state.reportPath && (
        <section className="bg-white px-32p py-80p">
          <div className="mx-auto max-w-7xl flex flex-wrap items-center justify-between gap-4">
            <p className="font-display text-feature text-slate-mid">
              Report saved to <code className="text-dark">{state.reportPath}</code>
            </p>
            <Link to="/history">
              <Button variant="primary">Open in history</Button>
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}

function ActivityFeed({
  messages,
  toolCalls,
}: {
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

  return (
    <Card className="max-h-[80vh] overflow-hidden flex flex-col">
      <h2 className="font-display text-card font-medium mb-4">Activity</h2>
      <div ref={ref} className="flex-1 overflow-y-auto space-y-3 pr-2">
        {items.map((it, idx) => (
          <div key={idx} className="border-b border-slate-tone/60 pb-2 last:border-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-display text-xs text-slate-cool">
                {it.ts.slice(11, 19)}
              </span>
              <span className="font-display text-xs uppercase tracking-wider text-slate-mid">
                {it.kind}
              </span>
            </div>
            <p className="text-body-em text-dark break-words">
              {it.text.length > 280 ? it.text.slice(0, 280) + "…" : it.text}
            </p>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-slate-mid text-body">Waiting for events…</p>
        )}
      </div>
    </Card>
  );
}
