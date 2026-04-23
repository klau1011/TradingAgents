"""Event schema for AnalysisRunner.

Events form the wire contract between the headless runner, the CLI presentation
layer, and the web dashboard. They are dataclasses with a ``to_dict`` helper so
they can be JSON-serialized for the WebSocket transport.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


RunStatus = Literal["queued", "running", "done", "error", "cancelled"]
AgentStatus = Literal["pending", "in_progress", "completed", "error"]


@dataclass
class StatusEvent:
    """Top-level run lifecycle event."""

    status: RunStatus
    type: str = "status"
    queue_position: Optional[int] = None
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class AgentStatusEvent:
    agent: str
    status: AgentStatus
    type: str = "agent_status"
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class MessageEvent:
    message_type: str  # "User" | "Agent" | "Data" | "Control" | "System"
    content: str
    type: str = "message"
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class ToolCallEvent:
    tool_name: str
    args: Dict[str, Any]
    type: str = "tool_call"
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class ReportSectionEvent:
    section: str
    content: str
    type: str = "report_section"
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class DoneEvent:
    decision: str
    final_state_path: Optional[str] = None
    report_path: Optional[str] = None
    type: str = "done"
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class ErrorEvent:
    message: str
    type: str = "error"
    timestamp: str = field(default_factory=_now_iso)


RunEvent = Union[
    StatusEvent,
    AgentStatusEvent,
    MessageEvent,
    ToolCallEvent,
    ReportSectionEvent,
    DoneEvent,
    ErrorEvent,
]


def event_to_dict(event: RunEvent) -> Dict[str, Any]:
    """Serialize a run event to a plain dict suitable for JSON encoding."""
    return asdict(event)
