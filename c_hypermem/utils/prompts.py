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
    def __init__(self, package: str = "c_hypermem.prompts") -> None:
        self.package = package

    def load(self, prompt_id: str) -> Prompt:
        rel_path = PurePosixPath(*prompt_id.split(".")).with_suffix(".md")
        resource = resources.files(self.package).joinpath(str(rel_path))
        text = resource.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return Prompt(id=prompt_id, text=text, hash=f"sha256:{digest}")

    def combined_hash(self, prompt_ids: list[str]) -> str:
        digests = [self.load(prompt_id).hash for prompt_id in prompt_ids]
        payload = "\n".join(sorted(digests))
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

