from __future__ import annotations

from c_hypermem.schema import SharedNode, ViewEdge


class GraphMaintenance:
    """Placeholder for merge, contradiction and stale-state maintenance."""

    def apply(self, nodes: list[SharedNode], edges: list[ViewEdge]) -> tuple[list[SharedNode], list[ViewEdge]]:
        return nodes, edges

