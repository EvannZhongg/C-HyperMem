from __future__ import annotations

from typing import Any, Protocol

from c_hypermem.schema import SharedNode, ViewEdge


class ViewProjector(Protocol):
    """Projects extracted nodes into multi-view hyperedges."""

    def project(
        self,
        nodes: list[SharedNode],
        *,
        namespace: str,
        metadata: dict[str, Any],
        current_turn: int,
    ) -> list[ViewEdge]: ...

