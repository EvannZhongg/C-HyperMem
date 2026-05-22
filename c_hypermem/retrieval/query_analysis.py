from __future__ import annotations

import re
from dataclasses import dataclass

from c_hypermem.utils.text import tokenize


@dataclass(frozen=True)
class QueryAnalysis:
    query: str
    tokens: list[str]
    entity_hints: list[str]
    time_hints: list[str]
    asks_preference: bool
    asks_task: bool


class QueryAnalyzer:
    def analyze(self, query: str) -> QueryAnalysis:
        tokens = tokenize(query)
        entity_hints = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", query)
        time_hints = re.findall(r"\b\d{4}(?:[-/]\d{1,2})?(?:[-/]\d{1,2})?\b", query)
        lowered = query.lower()
        return QueryAnalysis(
            query=query,
            tokens=tokens,
            entity_hints=entity_hints,
            time_hints=time_hints,
            asks_preference=any(word in lowered for word in ["prefer", "like", "favorite", "favourite"]),
            asks_task=any(word in lowered for word in ["plan", "goal", "task", "deadline", "schedule"]),
        )

