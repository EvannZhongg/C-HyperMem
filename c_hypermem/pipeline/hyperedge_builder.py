from __future__ import annotations

from typing import Any, Protocol

from c_hypermem.schema import HyperEdge, MemoryNode


class HyperEdgeBuilder(Protocol):
    """Builds or updates HyperEdges from extracted memory nodes."""

    def build(
        self,
        nodes: list[MemoryNode],
        *,
        namespace: str,
        metadata: dict[str, Any],
        current_turn: int,
    ) -> list[HyperEdge]: ...

