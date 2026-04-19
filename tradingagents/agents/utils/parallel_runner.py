"""Parallel analyst runner.

Wraps an analyst node + its tool node into a single graph node that runs the
``analyst -> tools -> analyst -> ...`` loop entirely in-process against a
*local* message buffer. This keeps each analyst's tool-calling history isolated
from sibling analysts so multiple analysts can execute in parallel without
racing on the shared ``messages`` channel.

The wrapper writes only the analyst's report field plus the accumulated
messages back to parent state. ``add_messages`` (the default reducer on
``MessagesState``) merges concurrent message batches by id, so parallel
branches do not corrupt each other.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List


def create_parallel_analyst_runner(
    analyst_node: Callable[[Dict[str, Any]], Dict[str, Any]],
    tool_node: Any,
    report_key: str,
    max_iterations: int = 10,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Return a graph node that runs an analyst's tool-calling loop in isolation.

    Args:
        analyst_node: The analyst node function (e.g. ``market_analyst_node``).
        tool_node: The ``ToolNode`` bound to the same toolset as the analyst.
        report_key: State key the analyst writes its final report to
            (e.g. ``"market_report"``).
        max_iterations: Safety cap on tool-call rounds per analyst.
    """

    def runner(state: Dict[str, Any]) -> Dict[str, Any]:
        # Snapshot just the messages so each parallel analyst gets its own
        # private conversation buffer and never observes a sibling's tool calls.
        local_state = dict(state)
        local_messages: List[Any] = list(state.get("messages", []))
        local_state["messages"] = local_messages

        emitted: List[Any] = []
        report = ""

        for _ in range(max_iterations):
            result = analyst_node(local_state)

            new_msgs = result.get("messages", []) or []
            emitted.extend(new_msgs)
            local_messages = local_messages + list(new_msgs)
            local_state["messages"] = local_messages

            last = new_msgs[-1] if new_msgs else None
            has_tool_calls = bool(getattr(last, "tool_calls", None)) if last else False

            if has_tool_calls:
                tool_result = tool_node.invoke({"messages": local_messages})
                tool_msgs = list(tool_result.get("messages", []) or [])
                emitted.extend(tool_msgs)
                local_messages = local_messages + tool_msgs
                local_state["messages"] = local_messages
                continue

            report = result.get(report_key, "") or ""
            break

        return {report_key: report, "messages": emitted}

    return runner
