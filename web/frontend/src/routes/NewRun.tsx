import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Button } from "../components/ui/Button";
import { Card, SectionHeading } from "../components/ui/Card";

export function NewRunPage() {
  const navigate = useNavigate();
  const { data: opts, isLoading } = useQuery({
    queryKey: ["options"],
    queryFn: api.options,
  });

  const today = new Date().toISOString().slice(0, 10);
  const [ticker, setTicker] = useState("SPY");
  const [date, setDate] = useState(today);
  const [analysts, setAnalysts] = useState<string[]>([
    "market",
    "social",
    "news",
    "fundamentals",
  ]);
  const [provider, setProvider] = useState("openai");
  const [shallow, setShallow] = useState("gpt-5.4-mini");
  const [deep, setDeep] = useState("gpt-5.4");
  const [depth, setDepth] = useState(1);
  const [language, setLanguage] = useState("English");
  // Provider-specific thinking depth. Mirrors the CLI's Step 8.
  const [openaiEffort, setOpenaiEffort] = useState("medium");
  const [anthropicEffort, setAnthropicEffort] = useState("high");
  const [googleThinking, setGoogleThinking] = useState("high");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const providerModels =
    opts?.models[provider] ?? { quick: [], deep: [] as [string, string][] };
  const keyStatus = opts?.api_key_status[provider];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const run = await api.startRun({
        ticker,
        analysis_date: date,
        analysts,
        research_depth: depth,
        llm_provider: provider,
        shallow_thinker: shallow,
        deep_thinker: deep,
        output_language: language,
        openai_reasoning_effort:
          provider === "openai" ? openaiEffort : null,
        anthropic_effort:
          provider === "anthropic" ? anthropicEffort : null,
        google_thinking_level:
          provider === "google" ? googleThinking : null,
      });
      navigate(`/runs/${run.run_id}`);
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  function toggleAnalyst(key: string) {
    setAnalysts((cur) =>
      cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]
    );
  }

  if (isLoading || !opts)
    return <div className="p-32p text-body text-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-5xl px-32p py-80p space-y-80p">
      <header className="space-y-6">
        <h1 className="font-display text-display-hero font-medium text-fg">
          Run an analysis.
        </h1>
        <p className="text-body-lg text-muted max-w-2xl">
          Spin up a multi-agent debate over your ticker. Up to three runs
          execute concurrently — extras are queued.
        </p>
      </header>

      <Card className="space-y-32p">
        <form onSubmit={submit} className="space-y-32p">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-32p">
            <Field label="Ticker">
              <input
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                className={inputCls}
                placeholder="SPY, CNC.TO, 7203.T"
                required
              />
            </Field>
            <Field label="Analysis date">
              <input
                type="date"
                value={date}
                max={today}
                onChange={(e) => setDate(e.target.value)}
                className={inputCls}
                required
              />
            </Field>
          </div>

          <Field label="Analysts">
            <div className="flex flex-wrap gap-3">
              {opts.analysts.map((a) => {
                const on = analysts.includes(a.key);
                return (
                  <button
                    type="button"
                    key={a.key}
                    onClick={() => toggleAnalyst(a.key)}
                    className={`rounded-pill px-32p py-3 font-display text-body-em border-2 transition-opacity ${
                      on
                        ? "bg-inverse text-inverse-fg border-inverse"
                        : "bg-canvas text-fg border-edge hover:opacity-85"
                    }`}
                  >
                    {a.label}
                  </button>
                );
              })}
            </div>
          </Field>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-32p">
            <Field label="Provider">
              <select
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value);
                  const m = opts.models[e.target.value];
                  if (m?.quick?.[0]) setShallow(m.quick[0][1]);
                  if (m?.deep?.[0]) setDeep(m.deep[0][1]);
                }}
                className={inputCls}
              >
                {opts.providers.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              {keyStatus && (
                <p
                  className={`mt-2 text-body-em ${
                    keyStatus.set ? "text-rui-teal" : "text-rui-danger"
                  }`}
                >
                  {keyStatus.set
                    ? `API key ✓ (${keyStatus.env_vars.join(", ") || "local"})`
                    : `Missing env var: ${keyStatus.env_vars.join(", ")}`}
                </p>
              )}
            </Field>
            <Field label="Quick-think model">
              <select
                value={shallow}
                onChange={(e) => setShallow(e.target.value)}
                className={inputCls}
              >
                {providerModels.quick.map(([label, value]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Deep-think model">
              <select
                value={deep}
                onChange={(e) => setDeep(e.target.value)}
                className={inputCls}
              >
                {providerModels.deep.map(([label, value]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-32p">
            <Field label="Research depth">
              <select
                value={depth}
                onChange={(e) => setDepth(Number(e.target.value))}
                className={inputCls}
              >
                {opts.research_depths.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Output language">
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className={inputCls}
              >
                {opts.languages.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {provider === "openai" && (
            <Field label="Reasoning effort">
              <select
                value={openaiEffort}
                onChange={(e) => setOpenaiEffort(e.target.value)}
                className={inputCls}
              >
                <option value="low">Low (faster)</option>
                <option value="medium">Medium (default)</option>
                <option value="high">High (more thorough)</option>
              </select>
            </Field>
          )}
          {provider === "anthropic" && (
            <Field label="Effort level">
              <select
                value={anthropicEffort}
                onChange={(e) => setAnthropicEffort(e.target.value)}
                className={inputCls}
              >
                <option value="low">Low (faster, cheaper)</option>
                <option value="medium">Medium (balanced)</option>
                <option value="high">High (recommended)</option>
              </select>
            </Field>
          )}
          {provider === "google" && (
            <Field label="Thinking mode">
              <select
                value={googleThinking}
                onChange={(e) => setGoogleThinking(e.target.value)}
                className={inputCls}
              >
                <option value="high">Enable thinking (recommended)</option>
                <option value="minimal">Minimal / disable thinking</option>
              </select>
            </Field>
          )}

          {err && <p className="text-rui-danger text-body">{err}</p>}

          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={submitting || analysts.length === 0}>
              {submitting ? "Starting…" : "Run analysis"}
            </Button>
            <Button
              type="button"
              variant="outlined"
              onClick={() => navigate("/history")}
            >
              View history
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

const inputCls =
  "w-full bg-canvas text-fg text-body border-2 border-edge rounded-sm px-4 py-3 " +
  "focus:outline-none focus:border-fg transition-colors";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block font-display text-body-em font-medium text-muted mb-2 uppercase tracking-wider text-xs">
        {label}
      </span>
      {children}
    </label>
  );
}

// silence unused-import linter for SectionHeading (kept for future use)
void SectionHeading;
