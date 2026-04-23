/** Wire-format mirroring tradingagents/runner_events.py */

export type RunStatus = "queued" | "running" | "done" | "error" | "cancelled";
export type AgentStatus = "pending" | "in_progress" | "completed" | "error";

export interface StatusEvent {
  type: "status";
  status: RunStatus;
  queue_position: number | null;
  timestamp: string;
}
export interface AgentStatusEvent {
  type: "agent_status";
  agent: string;
  status: AgentStatus;
  timestamp: string;
}
export interface MessageEvent {
  type: "message";
  message_type: string;
  content: string;
  timestamp: string;
}
export interface ToolCallEvent {
  type: "tool_call";
  tool_name: string;
  args: Record<string, unknown>;
  timestamp: string;
}
export interface ReportSectionEvent {
  type: "report_section";
  section: string;
  content: string;
  timestamp: string;
}
export interface DoneEvent {
  type: "done";
  decision: string;
  final_state_path: string | null;
  report_path: string | null;
  timestamp: string;
}
export interface ErrorEvent {
  type: "error";
  message: string;
  timestamp: string;
}

export type RunEvent =
  | StatusEvent
  | AgentStatusEvent
  | MessageEvent
  | ToolCallEvent
  | ReportSectionEvent
  | DoneEvent
  | ErrorEvent;

export interface RunSummary {
  run_id: string;
  ticker: string;
  analysis_date: string;
  status: RunStatus;
  queue_position: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  decision: string | null;
  report_path: string | null;
  error: string | null;
}

export interface RunDetail extends RunSummary {
  events: RunEvent[];
}

export interface ConfigOptions {
  analysts: { key: string; label: string }[];
  research_depths: { value: number; label: string }[];
  providers: string[];
  models: Record<string, Record<"quick" | "deep", [string, string][]>>;
  api_key_status: Record<
    string,
    { required: boolean; set: boolean; env_vars: string[] }
  >;
  languages: string[];
}

export interface ReportSummary {
  folder: string;
  ticker: string;
  timestamp: string;
  decision: string | null;
  path: string;
}
export interface ReportDetail {
  folder: string;
  ticker: string;
  briefing: string | null;
  complete_report: string;
  sections: Record<string, Record<string, string>>;
  decision: string | null;
  path: string;
}

export const SECTION_LABELS: Record<string, string> = {
  market_report: "Market Analysis",
  sentiment_report: "Social Sentiment",
  news_report: "News Analysis",
  fundamentals_report: "Fundamentals",
  investment_plan: "Research Decision",
  trader_investment_plan: "Trading Plan",
  final_trade_decision: "Portfolio Decision",
};
