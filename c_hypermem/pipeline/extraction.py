from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from c_hypermem.schema import IngestionOutput, Message


@dataclass(frozen=True)
class ExtractionContext:
    namespace: str
    metadata: dict[str, Any]
    current_turn: int


class MemoryExtractor(Protocol):
    """Produces memory nodes and optional hyperedges from normalized messages."""

    def extract(self, messages: list[Message], context: ExtractionContext) -> IngestionOutput: ...
