import { useEffect, useReducer, useRef } from "react";
import { streamUrl } from "../api";
import type {
  AgentStatus,
  RunEvent,
  RunStatus,
} from "../types";

interface RunState {
  status: RunStatus;
  queuePosition: number | null;
  agents: Record<string, AgentStatus>;
  agentOrder: string[];
  messages: { ts: string; type: string; content: string }[];
  toolCalls: { ts: string; name: string; args: Record<string, unknown> }[];
  reports: Record<string, string>;
  decision: string | null;
  reportPath: string | null;
  error: string | null;
  connected: boolean;
}

const createInitialState = (): RunState => ({
  status: "queued",
  queuePosition: null,
  agents: {},
  agentOrder: [],
  messages: [],
  toolCalls: [],
  reports: {},
  decision: null,
  reportPath: null,
  error: null,
  connected: false,
});

const initial: RunState = createInitialState();

type Action =
  | { type: "reset" }
  | { type: "event"; event: RunEvent }
  | { type: "connected" }
  | { type: "disconnected" };

function reducer(state: RunState, action: Action): RunState {
  if (action.type === "reset") return createInitialState();
  if (action.type === "connected") return { ...state, connected: true };
  if (action.type === "disconnected") return { ...state, connected: false };
  const e = action.event;
  switch (e.type) {
    case "status":
      return { ...state, status: e.status, queuePosition: e.queue_position };
    case "agent_status": {
      const known = state.agents[e.agent] !== undefined;
      return {
        ...state,
        agents: { ...state.agents, [e.agent]: e.status },
        agentOrder: known ? state.agentOrder : [...state.agentOrder, e.agent],
      };
    }
    case "message":
      return {
        ...state,
        messages: [
          ...state.messages.slice(-199),
          { ts: e.timestamp, type: e.message_type, content: e.content },
        ],
      };
    case "tool_call":
      return {
        ...state,
        toolCalls: [
          ...state.toolCalls.slice(-99),
          { ts: e.timestamp, name: e.tool_name, args: e.args },
        ],
      };
    case "report_section":
      return {
        ...state,
        reports: { ...state.reports, [e.section]: e.content },
      };
    case "done":
      return {
        ...state,
        decision: e.decision,
        reportPath: e.report_path,
      };
    case "error":
      return { ...state, error: e.message };
    default:
      return state;
  }
}

export function useRunStream(runId: string | undefined): RunState {
  const [state, dispatch] = useReducer(reducer, initial);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    dispatch({ type: "reset" });
    if (!runId) return;
    const ws = new WebSocket(streamUrl(runId));
    wsRef.current = ws;
    ws.onopen = () => dispatch({ type: "connected" });
    ws.onclose = () => dispatch({ type: "disconnected" });
    ws.onmessage = (ev) => {
      try {
        const event = JSON.parse(ev.data) as RunEvent;
        dispatch({ type: "event", event });
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => {
      ws.close();
    };
  }, [runId]);

  return state;
}
