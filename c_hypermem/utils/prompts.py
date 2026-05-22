from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib import resources
from pathlib import PurePosixPath


@dataclass(frozen=True)
class Prompt:
    id: str
    text: str
    hash: str


class PromptRegistry:
    PROMPT_PATHS = {
        "extraction.fact": "extraction/fact_extraction.md",
        "extraction.entity": "extraction/entity_extraction.md",
        "local_graph.event": "local_graph/event_local_graph.md",
        "local_graph.fact": "local_graph/fact_local_graph.md",
        "views.provenance_view": "views/provenance_view.md",
        "views.entity_state_view": "views/entity_state_view.md",
        "views.temporal_view": "views/temporal_view.md",
        "views.topic_or_intent_view": "views/topic_or_intent_view.md",
        "views.preference_profile_view": "views/preference_profile_view.md",
        "retrieval.query_analysis": "retrieval/query_analysis.md",
        "maintenance.fact_merge": "maintenance/fact_merge.md",
        "maintenance.contradiction_check": "maintenance/contradiction_check.md",
    }

    def __init__(self, package: str = "c_hypermem.prompts") -> None:
        self.package = package

    def load(self, prompt_id: str) -> Prompt:
        rel_path = PurePosixPath(self.PROMPT_PATHS.get(prompt_id, str(PurePosixPath(*prompt_id.split(".")).with_suffix(".md"))))
        resource = resources.files(self.package).joinpath(str(rel_path))
        text = resource.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return Prompt(id=prompt_id, text=text, hash=f"sha256:{digest}")

    def combined_hash(self, prompt_ids: list[str]) -> str:
        digests = [self.load(prompt_id).hash for prompt_id in prompt_ids]
        payload = "\n".join(sorted(digests))
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
