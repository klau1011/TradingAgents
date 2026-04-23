import { useEffect, useReducer, useRef } from "react";
import { api, streamUrl } from "../api";
import type {
  AgentStatus,
  RunEvent,
  RunStatus,
} from "../types";

const MESSAGE_KEY_CAP = 400;
const TOOL_KEY_CAP = 300;
const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000, 10000] as const;

export interface AgentTimelineEntry {
  startedAt?: string;
  completedAt?: string;
  erroredAt?: string;
}

interface RunState {
  status: RunStatus;
  queuePosition: number | null;
  agents: Record<string, AgentStatus>;
  agentOrder: string[];
  /** Per-agent first/last transition timestamps for the Gantt view. */
  agentTimeline: Record<string, AgentTimelineEntry>;
  messages: { ts: string; type: string; content: string }[];
  toolCalls: { ts: string; name: string; args: Record<string, unknown> }[];
  reports: Record<string, string>;
  decision: string | null;
  reportPath: string | null;
  error: string | null;
  /** Earliest event timestamp seen — used as the timeline T0. */
  runStartedAt: string | null;
  runFinishedAt: string | null;
  connected: boolean;
  reconnecting: boolean;
  /** True while the initial REST backfill is in flight. */
  backfilling: boolean;
  lastError: string | null;
}

const createInitialState = (): RunState => ({
  status: "queued",
  queuePosition: null,
  agents: {},
  agentOrder: [],
  agentTimeline: {},
  messages: [],
  toolCalls: [],
  reports: {},
  decision: null,
  reportPath: null,
  error: null,
  runStartedAt: null,
  runFinishedAt: null,
  connected: false,
  reconnecting: false,
  backfilling: false,
  lastError: null,
});

const initial: RunState = createInitialState();

type Action =
  | { type: "reset" }
  | { type: "event"; event: RunEvent }
  | { type: "backfill_start" }
  | { type: "backfill_done" }
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "reconnecting" }
  | { type: "connection_error"; message: string };

function applyAgentTimeline(
  current: Record<string, AgentTimelineEntry>,
  agent: string,
  status: AgentStatus,
  ts: string
): Record<string, AgentTimelineEntry> {
  const prev = current[agent] ?? {};
  let next: AgentTimelineEntry = prev;
  if (status === "in_progress" && !prev.startedAt) {
    next = { ...prev, startedAt: ts };
  } else if (status === "completed") {
    next = {
      ...prev,
      startedAt: prev.startedAt ?? ts,
      completedAt: ts,
    };
  } else if (status === "error") {
    next = {
      ...prev,
      startedAt: prev.startedAt ?? ts,
      erroredAt: ts,
    };
  }
  if (next === prev) return current;
  return { ...current, [agent]: next };
}

function reducer(state: RunState, action: Action): RunState {
  if (action.type === "reset") return createInitialState();
  if (action.type === "backfill_start")
    return { ...state, backfilling: true };
  if (action.type === "backfill_done")
    return { ...state, backfilling: false };
  if (action.type === "connected") {
    return {
      ...state,
      connected: true,
      reconnecting: false,
      lastError: null,
    };
  }
  if (action.type === "disconnected") return { ...state, connected: false };
  if (action.type === "reconnecting") {
    return { ...state, reconnecting: true };
  }
  if (action.type === "connection_error") {
    return { ...state, lastError: action.message };
  }
  const e = action.event;
  // Track earliest/latest wall-clock for timeline axis.
  const runStartedAt =
    state.runStartedAt && state.runStartedAt < e.timestamp
      ? state.runStartedAt
      : e.timestamp;
  switch (e.type) {
    case "status": {
      const finished =
        e.status === "done" || e.status === "error" || e.status === "cancelled";
      return {
        ...state,
        status: e.status,
        queuePosition: e.queue_position,
        runStartedAt,
        runFinishedAt: finished ? e.timestamp : state.runFinishedAt,
      };
    }
    case "agent_status": {
      const known = state.agents[e.agent] !== undefined;
      return {
        ...state,
        agents: { ...state.agents, [e.agent]: e.status },
        agentOrder: known ? state.agentOrder : [...state.agentOrder, e.agent],
        agentTimeline: applyAgentTimeline(
          state.agentTimeline,
          e.agent,
          e.status,
          e.timestamp
        ),
        runStartedAt,
      };
    }
    case "message":
      return {
        ...state,
        messages: [
          ...state.messages.slice(-199),
          { ts: e.timestamp, type: e.message_type, content: e.content },
        ],
        runStartedAt,
      };
    case "tool_call":
      return {
        ...state,
        toolCalls: [
          ...state.toolCalls.slice(-99),
          { ts: e.timestamp, name: e.tool_name, args: e.args },
        ],
        runStartedAt,
      };
    case "report_section":
      return {
        ...state,
        reports: { ...state.reports, [e.section]: e.content },
        runStartedAt,
      };
    case "done":
      return {
        ...state,
        status: "done",
        decision: e.decision,
        reportPath: e.report_path,
        runStartedAt,
        runFinishedAt: e.timestamp,
      };
    case "error":
      return {
        ...state,
        status: "error",
        error: e.message,
        runStartedAt,
        runFinishedAt: e.timestamp,
      };
    default:
      return state;
  }
}

function pushSeen(set: Set<string>, key: string, cap: number): boolean {
  if (set.has(key)) return false;
  set.add(key);
  if (set.size > cap) {
    const oldest = set.values().next().value as string | undefined;
    if (oldest) set.delete(oldest);
  }
  return true;
}

function eventDedupeKey(event: RunEvent): string | null {
  if (event.type === "message") {
    return `${event.timestamp}|${event.message_type}|${event.content.length}|${event.content.slice(0, 80)}`;
  }
  if (event.type === "tool_call") {
    return `${event.timestamp}|${event.tool_name}|${JSON.stringify(event.args)}`;
  }
  return null;
}

export function useRunStream(runId: string | undefined): RunState {
  const [state, dispatch] = useReducer(reducer, initial);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const statusRef = useRef<RunStatus>("queued");
  const seenMessageKeysRef = useRef(new Set<string>());
  const seenToolCallKeysRef = useRef(new Set<string>());

  useEffect(() => {
    statusRef.current = state.status;
  }, [state.status]);

  useEffect(() => {
    dispatch({ type: "reset" });
    if (!runId) return;

    reconnectAttemptRef.current = 0;
    seenMessageKeysRef.current.clear();
    seenToolCallKeysRef.current.clear();

    let disposed = false;

    /** Replay an event through the reducer + dedup sets. */
    const ingest = (event: RunEvent) => {
      const key = eventDedupeKey(event);
      if (event.type === "message" && key) {
        if (!pushSeen(seenMessageKeysRef.current, key, MESSAGE_KEY_CAP)) {
          return;
        }
      }
      if (event.type === "tool_call" && key) {
        if (!pushSeen(seenToolCallKeysRef.current, key, TOOL_KEY_CAP)) {
          return;
        }
      }
      dispatch({ type: "event", event });
    };

    const connect = () => {
      if (disposed) return;

      const ws = new WebSocket(streamUrl(runId));
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        dispatch({ type: "connected" });
      };

      ws.onerror = () => {
        dispatch({
          type: "connection_error",
          message: "Connection interrupted. Reconnecting…",
        });
      };

      ws.onclose = () => {
        dispatch({ type: "disconnected" });
        if (disposed) return;
        if (
          statusRef.current === "done" ||
          statusRef.current === "error" ||
          statusRef.current === "cancelled"
        ) {
          return;
        }

        dispatch({ type: "reconnecting" });
        const idx = Math.min(
          reconnectAttemptRef.current,
          RECONNECT_DELAYS_MS.length - 1
        );
        const delay = RECONNECT_DELAYS_MS[idx];
        reconnectAttemptRef.current += 1;
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectTimeoutRef.current = null;
          connect();
        }, delay);
      };

      ws.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data) as RunEvent;
          ingest(event);
        } catch {
          /* ignore malformed frames */
        }
      };
    };

    // Backfill via REST first so a refresh shows existing context immediately,
    // then attach the WebSocket. Dedup sets prevent the WS replay from
    // double-counting messages/tool_calls. Other event kinds are idempotent.
    dispatch({ type: "backfill_start" });
    api
      .getRun(runId)
      .then((detail) => {
        if (disposed) return;
        for (const ev of detail.events) {
          ingest(ev as RunEvent);
        }
      })
      .catch(() => {
        // Backfill failure isn't fatal — the WS may still attach.
      })
      .finally(() => {
        if (disposed) return;
        dispatch({ type: "backfill_done" });
        connect();
      });

    return () => {
      disposed = true;
      if (reconnectTimeoutRef.current !== null) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [runId]);

  return state;
}
