"""Pure trajectory normalization helpers shared across adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrajectoryEvent:
    """Normalized low-level event from a raw trajectory."""

    index: int
    kind: str
    label: str
    excerpt: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class ToolInteraction:
    """Paired tool call and result linked by call id."""

    index: int
    tool_name: str
    short_name: str
    call_id: str
    short_call_id: str
    call_event: TrajectoryEvent | None = None
    result_event: TrajectoryEvent | None = None


@dataclass(frozen=True)
class StepTimelineItem:
    """Display row inside one trajectory step."""

    kind: str
    index: int
    title: str
    event: TrajectoryEvent | None = None
    interaction: ToolInteraction | None = None


def extract_trajectory(data: Any) -> dict[str, Any] | None:
    """Return a supported trajectory object from wrapped or bare JSON."""
    if not isinstance(data, dict):
        return None
    wrapped = data.get("trajectory")
    if isinstance(wrapped, dict) and isinstance(wrapped.get("steps"), list):
        return wrapped
    if isinstance(data.get("steps"), list):
        return data
    return None


def normalize_events(trajectory: dict[str, Any]) -> list[TrajectoryEvent]:
    """Return normalized low-level events from a supported trajectory object."""
    events: list[TrajectoryEvent] = []
    steps = trajectory.get("steps")
    if not isinstance(steps, list):
        return events

    for step in steps:
        if not isinstance(step, dict):
            continue
        outputs = step.get("output")
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            if not isinstance(output, dict):
                continue
            kind = str(output.get("type") or "event")
            events.append(
                TrajectoryEvent(
                    index=len(events),
                    kind=kind,
                    label=_event_label(output),
                    excerpt=_event_excerpt(output),
                    raw=output,
                )
            )
    return events


def normalize_step_events(trajectory: dict[str, Any]) -> list[list[TrajectoryEvent]]:
    """Return normalized events grouped by top-level step."""
    groups: list[list[TrajectoryEvent]] = []
    steps = trajectory.get("steps")
    if not isinstance(steps, list):
        return groups

    index = 0
    for step in steps:
        group: list[TrajectoryEvent] = []
        if isinstance(step, dict) and isinstance(step.get("output"), list):
            for output in step["output"]:
                if not isinstance(output, dict):
                    continue
                kind = str(output.get("type") or "event")
                event = TrajectoryEvent(
                    index=index,
                    kind=kind,
                    label=_event_label(output),
                    excerpt=_event_excerpt(output),
                    raw=output,
                )
                group.append(event)
                index += 1
        groups.append(group)
    return groups


def normalize_step_overlay(
    trajectory: dict[str, Any],
) -> tuple[list[list[TrajectoryEvent]], list[list[StepTimelineItem]]]:
    """Return grouped trajectory events plus their paired timeline rows."""
    step_events = normalize_step_events(trajectory)
    return step_events, _normalize_step_timeline_from_events(step_events)


def _normalize_step_timeline_from_events(
    step_events: list[list[TrajectoryEvent]],
) -> list[list[StepTimelineItem]]:
    """Return per-step display rows from pre-normalized events."""
    timeline_groups: list[list[StepTimelineItem]] = []
    for events in step_events:
        group: list[StepTimelineItem] = []
        pending_calls: dict[str, int] = {}
        for event in events:
            if event.kind == "function_call":
                interaction = ToolInteraction(
                    index=event.index,
                    tool_name=_tool_name(event.raw),
                    short_name=_short_tool_name(_tool_name(event.raw)),
                    call_id=_call_id(event.raw),
                    short_call_id=_short_call_id(_call_id(event.raw)),
                    call_event=event,
                )
                group.append(
                    StepTimelineItem(
                        kind="tool",
                        index=event.index,
                        title=_tool_tree_title(interaction),
                        interaction=interaction,
                    )
                )
                if interaction.call_id:
                    pending_calls[interaction.call_id] = len(group) - 1
                continue

            if event.kind == "function_call_result":
                call_id = _call_id(event.raw)
                group_index = pending_calls.pop(call_id, None) if call_id else None
                if group_index is not None:
                    interaction = group[group_index].interaction
                    if interaction is None:
                        continue
                    updated = ToolInteraction(
                        index=interaction.index,
                        tool_name=interaction.tool_name,
                        short_name=interaction.short_name,
                        call_id=interaction.call_id,
                        short_call_id=interaction.short_call_id,
                        call_event=interaction.call_event,
                        result_event=event,
                    )
                    group[group_index] = StepTimelineItem(
                        kind="tool",
                        index=updated.index,
                        title=_tool_tree_title(updated),
                        interaction=updated,
                    )
                    continue

                orphan = ToolInteraction(
                    index=event.index,
                    tool_name=_tool_name(event.raw),
                    short_name=_short_tool_name(_tool_name(event.raw)),
                    call_id=call_id,
                    short_call_id=_short_call_id(call_id),
                    result_event=event,
                )
                group.append(
                    StepTimelineItem(
                        kind="tool",
                        index=event.index,
                        title=_tool_tree_title(orphan, suffix=" Output"),
                        interaction=orphan,
                    )
                )
                continue

            group.append(
                StepTimelineItem(
                    kind=event.kind,
                    index=event.index,
                    title=_standalone_tree_title(event),
                    event=event,
                )
            )
        timeline_groups.append(group)
    return timeline_groups


def _event_label(raw: dict[str, Any]) -> str:
    for key in ("role", "name", "callId", "call_id"):
        value = raw.get(key)
        if value:
            return str(value)
    return ""


def _tool_name(raw: dict[str, Any]) -> str:
    value = raw.get("name")
    return str(value) if value else "tool"


def _call_id(raw: dict[str, Any]) -> str:
    value = raw.get("callId") or raw.get("call_id")
    return str(value) if value else ""


def _short_tool_name(name: str) -> str:
    if "__" in name:
        return name.split("__")[-1]
    return name


def _short_call_id(call_id: str) -> str:
    if not call_id:
        return ""
    return call_id[-3:]


def _event_excerpt(raw: dict[str, Any]) -> str:
    text = _event_text(raw)
    if not text:
        text = _format_payload(_event_payload(raw))
    return _clip(_single_line(text), 96)


def _event_text(raw: dict[str, Any]) -> str:
    content = raw.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n\n".join(parts)
    if isinstance(content, str):
        return content
    return ""


def _event_payload(raw: dict[str, Any]) -> Any:
    if raw.get("type") == "function_call":
        return raw.get("arguments")
    if raw.get("type") == "function_call_result":
        return raw.get("output")
    return raw


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _decode_nested_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return _decode_nested_json(json.loads(value))
        except json.JSONDecodeError:
            return value
    if isinstance(value, list):
        return [_decode_nested_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode_nested_json(item) for key, item in value.items()}
    return value


def _format_payload(value: Any) -> str:
    decoded = _decode_nested_json(value)
    if isinstance(decoded, dict | list):
        return json.dumps(decoded, indent=2)
    if decoded is None:
        return ""
    return str(decoded)


def _tool_tree_title(interaction: ToolInteraction, suffix: str = "") -> str:
    prefix = f"{interaction.index + 1:03d} "
    title = interaction.short_name or interaction.tool_name
    call_id = f" #{interaction.short_call_id}" if interaction.short_call_id else ""
    return f"{prefix}{title}{call_id}{suffix}"


def _standalone_tree_title(event: TrajectoryEvent) -> str:
    prefix = f"{event.index + 1:03d} "
    label = event.label.title() if event.label else event.kind.replace("_", " ").title()
    return f"{prefix}{label}"
