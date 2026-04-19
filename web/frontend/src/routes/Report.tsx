import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api } from "../api";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { DecisionBadge } from "../components/ui/StatusBadge";

const SUBFOLDER_TITLES: Record<string, string> = {
  "1_analysts": "I. Analyst Team",
  "2_research": "II. Research Debate",
  "3_trading": "III. Trading Plan",
  "4_risk": "IV. Risk Management",
  "5_portfolio": "V. Portfolio Decision",
};

export function ReportPage() {
  const { folder } = useParams<{ folder: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["report", folder],
    queryFn: () => api.getReport(folder!),
    enabled: !!folder,
  });

  if (isLoading)
    return <div className="p-32p text-body text-slate-mid">Loading…</div>;
  if (error || !data)
    return (
      <div className="p-32p text-body text-rui-danger">
        Could not load report.
      </div>
    );

  return (
    <div className="space-y-0">
      <section className="bg-dark text-white px-32p py-80p">
        <div className="mx-auto max-w-5xl space-y-6">
          <p className="font-display text-nav text-slate-cool">{data.folder}</p>
          <h1 className="font-display text-display-hero font-medium">
            {data.ticker}
          </h1>
          <div className="flex items-center gap-4">
            {data.decision && <DecisionBadge decision={data.decision} />}
            <Link to="/history">
              <Button variant="ghost">Back to history</Button>
            </Link>
          </div>
        </div>
      </section>

      <section className="bg-surface px-32p py-80p">
        <div className="mx-auto max-w-5xl space-y-32p">
          <Card>
            <details open>
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

          {Object.entries(data.sections).map(([sub, files]) => (
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
