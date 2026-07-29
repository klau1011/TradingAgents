import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, AlertTriangle } from "lucide-react";

import { api } from "../api";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { DecisionBadge } from "../components/ui/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import { Skeleton, SkeletonCard, SkeletonText } from "../components/ui/Skeleton";

const SUBFOLDER_TITLES: Record<string, string> = {
  "0_summary": "Investor Briefing",
  "1_analysts": "I. Analyst Team",
  "2_research": "II. Research Debate",
  "3_trading": "III. Trading Plan",
  "4_risk": "IV. Risk Management",
  "5_portfolio": "V. Portfolio Decision",
};

type DecisionDetail = {
  rating: string;
  executive_summary: string;
  investment_thesis: string;
  price_target: number | null;
  time_horizon: string | null;
  confidence: string | null;
  what_would_change_it: string | null;
};

/** Optional string field: null when absent, blank, or the wrong type. */
function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeDecisionDetail(detail: unknown): DecisionDetail | null {
  if (!detail || typeof detail !== "object") {
    return null;
  }

  const candidate = detail as Record<string, unknown>;
  if (
    typeof candidate.rating !== "string" ||
    !candidate.rating.trim() ||
    typeof candidate.executive_summary !== "string" ||
    !candidate.executive_summary.trim() ||
    typeof candidate.investment_thesis !== "string" ||
    !candidate.investment_thesis.trim()
  ) {
    return null;
  }

  const priceTarget = candidate.price_target;
  if (
    priceTarget !== null &&
    priceTarget !== undefined &&
    (typeof priceTarget !== "number" || Number.isNaN(priceTarget))
  ) {
    return null;
  }

  const timeHorizon = candidate.time_horizon;
  if (
    timeHorizon !== null &&
    timeHorizon !== undefined &&
    typeof timeHorizon !== "string"
  ) {
    return null;
  }

  return {
    rating: candidate.rating.trim(),
    executive_summary: candidate.executive_summary.trim(),
    investment_thesis: candidate.investment_thesis.trim(),
    price_target: typeof priceTarget === "number" ? priceTarget : null,
    time_horizon: optionalString(timeHorizon),
    confidence: optionalString(candidate.confidence),
    what_would_change_it: optionalString(candidate.what_would_change_it),
  };
}

export function ReportPage() {
  const { folder } = useParams<{ folder: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["report", folder],
    queryFn: () => api.getReport(folder!),
    enabled: !!folder,
  });

  if (isLoading)
    return (
      <div className="space-y-0">
        <section className="bg-inverse text-inverse-fg px-32p py-80p">
          <div className="mx-auto max-w-5xl space-y-6">
            <Skeleton
              className="h-4 w-48 bg-inverse-fg/20"
              rounded="rounded-pill"
            />
            <Skeleton
              className="h-12 w-2/3 bg-inverse-fg/20"
              rounded="rounded-pill"
            />
            <SkeletonText lines={2} className="opacity-30" />
          </div>
        </section>
        <section className="bg-surface px-32p py-80p">
          <div className="mx-auto max-w-5xl space-y-32p">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </section>
      </div>
    );
  if (error || !data)
    return (
      <div className="mx-auto max-w-5xl px-32p py-80p">
        <EmptyState
          icon={AlertTriangle}
          title="Could not load report"
          description={
            error
              ? String(error)
              : "This report may have been moved or deleted."
          }
          action={
            <Link to="/history">
              <Button variant="primary">Back to history</Button>
            </Link>
          }
        />
      </div>
    );

  const decisionDetail = normalizeDecisionDetail(data.decision_detail);

  return (
    <div className="space-y-0">
      <section className="bg-inverse text-inverse-fg px-32p py-80p">
        <div className="mx-auto max-w-5xl space-y-6">
          <p className="font-display text-nav text-inverse-fg/60">{data.folder}</p>
          <h1 className="font-display text-display-hero font-medium">
            {data.ticker}
          </h1>
          <div className="flex items-center gap-4">
            {data.decision && <DecisionBadge decision={data.decision} />}
            <Link to="/history">
              <Button variant="ghost">
                <ArrowLeft size={16} aria-hidden="true" />
                Back to history
              </Button>
            </Link>
          </div>
          {decisionDetail &&
            (decisionDetail.price_target !== null ||
              decisionDetail.time_horizon ||
              decisionDetail.confidence) && (
              <dl className="flex flex-wrap gap-4">
                {decisionDetail.confidence && (
                  <div className="rounded-xl bg-inverse-fg/10 px-4 py-3">
                    <dt className="font-display text-nav text-inverse-fg/60">
                      Confidence
                    </dt>
                    <dd className="font-display text-feature font-medium capitalize">
                      {decisionDetail.confidence}
                    </dd>
                  </div>
                )}
                {decisionDetail.price_target !== null && (
                  <div className="rounded-xl bg-inverse-fg/10 px-4 py-3">
                    <dt className="font-display text-nav text-inverse-fg/60">
                      Price Target
                    </dt>
                    <dd className="font-display text-feature font-medium">
                      {decisionDetail.price_target}
                    </dd>
                  </div>
                )}
                {decisionDetail.time_horizon && (
                  <div className="rounded-xl bg-inverse-fg/10 px-4 py-3">
                    <dt className="font-display text-nav text-inverse-fg/60">
                      Time Horizon
                    </dt>
                    <dd className="font-display text-feature font-medium">
                      {decisionDetail.time_horizon}
                    </dd>
                  </div>
                )}
              </dl>
            )}
          {decisionDetail?.what_would_change_it && (
            <div className="rounded-xl bg-inverse-fg/10 px-4 py-3">
              <p className="font-display text-nav text-inverse-fg/60">
                What Would Change It
              </p>
              <p className="mt-1 text-inverse-fg/90">
                {decisionDetail.what_would_change_it}
              </p>
            </div>
          )}
        </div>
      </section>

      <section className="bg-surface px-32p py-80p">
        <div className="mx-auto max-w-5xl space-y-32p">
          {decisionDetail && (
            <>
              <Card>
                <div className="space-y-2">
                  <p className="font-display text-nav text-muted">
                    Portfolio Manager — action plan
                  </p>
                  <h2 className="font-display text-card font-medium">
                    Executive Summary
                  </h2>
                </div>
                <article className="md-body mt-4">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {decisionDetail.executive_summary}
                  </ReactMarkdown>
                </article>
              </Card>
              <Card>
                <div className="space-y-2">
                  <p className="font-display text-nav text-muted">
                    Portfolio Manager — reasoning
                  </p>
                  <h2 className="font-display text-card font-medium">
                    Investment Thesis
                  </h2>
                </div>
                <article className="md-body mt-4">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {decisionDetail.investment_thesis}
                  </ReactMarkdown>
                </article>
              </Card>
            </>
          )}

          {data.briefing && (
            <Card>
              <div className="space-y-2">
                <p className="font-display text-nav text-muted">
                  Plain-language summary for non-experts
                </p>
                <h2 className="font-display text-card font-medium">
                  Investor Briefing
                </h2>
              </div>
              <article className="md-body mt-4">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {data.briefing}
                </ReactMarkdown>
              </article>
            </Card>
          )}

          <Card>
            <details open={!data.briefing}>
              <summary className="cursor-pointer font-display text-card font-medium">
                Complete report
              </summary>
              <article className="md-body mt-4">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {data.complete_report}
                </ReactMarkdown>
              </article>
            </details>
          </Card>

          {Object.entries(data.sections)
            .filter(([sub]) => sub !== "0_summary")
            .map(([sub, files]) => (
            <Card key={sub}>
              <details>
                <summary className="cursor-pointer font-display text-card font-medium">
                  {SUBFOLDER_TITLES[sub] ?? sub}
                </summary>
                <div className="mt-4 space-y-32p">
                  {Object.entries(files).map(([name, content]) => (
                    <div key={name}>
                      <h3 className="font-display text-feature font-medium mb-2 capitalize">
                        {name.replace(/_/g, " ")}
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
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
