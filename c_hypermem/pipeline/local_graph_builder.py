from __future__ import annotations

from c_hypermem.schema import SharedNode


class LocalGraphBuilder:
    """M1 local graphs are produced during extraction; this hook is for M2 expansion."""

    def build(self, nodes: list[SharedNode]) -> list[SharedNode]:
        return nodes

