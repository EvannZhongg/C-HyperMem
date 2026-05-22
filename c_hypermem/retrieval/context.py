from __future__ import annotations

from c_hypermem.schema import SharedNode


def compose_result_content(node: SharedNode, views: list[str]) -> str:
    label = node.type.title()
    source = node.metadata.get("source_session_id")
    date = node.metadata.get("date") or node.time.world.event_time
    suffix_parts = []
    if source:
        suffix_parts.append(f"session={source}")
    if date:
        suffix_parts.append(f"date={date}")
    if views:
        suffix_parts.append(f"views={','.join(views)}")
    suffix = f"\nSource: {' '.join(suffix_parts)}" if suffix_parts else ""
    return f"[{label}] {node.content}{suffix}"

