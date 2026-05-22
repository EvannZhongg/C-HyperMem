from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from c_hypermem.errors import ConfigError


class StorageConfig(BaseModel):
    backend: str = "sqlite"
    path: str = "runs/c_hypermem/memory.sqlite3"


class IngestionConfig(BaseModel):
    event_mode: str = "interaction"
    incremental_build: bool = False
    extractor: str | None = None
    view_projector: str | None = None


class ViewsConfig(BaseModel):
    enabled: list[str] = Field(
        default_factory=lambda: [
            "provenance_view",
            "entity_state_view",
            "temporal_view",
        ]
    )


class RetrievalConfig(BaseModel):
    lexical_top_n: int = 30
    edge_top_n: int = 30
    rerank_top_n: int = 12
    use_view_expansion: bool = True
    use_temporal_filter: bool = True
    use_recency_decay: bool = True
    recency_decay_lambda: float = 0.03
    access_boost: float = 0.05


class MemoryConfig(BaseModel):
    storage: StorageConfig = Field(default_factory=StorageConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    views: ViewsConfig = Field(default_factory=ViewsConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    default_top_k: int = 10
    prompt_version: str = "0.1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, config: str | Path | dict[str, Any] | None = None) -> "MemoryConfig":
        if config is None:
            return cls()

        if isinstance(config, cls):
            return config

        if isinstance(config, dict):
            return cls.model_validate(_normalize_external_config(config))

        path = Path(config)
        if not path.exists():
            raise ConfigError(f"Config file does not exist: {path}")

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML config: {path}") from exc

        if not isinstance(raw, dict):
            raise ConfigError(f"Config must be a mapping: {path}")
        return cls.model_validate(_normalize_external_config(raw))

    def stable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"metadata"})


def _normalize_external_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept both standalone and agent_memory_eval-style config shapes."""
    data = dict(raw)

    storage_path = data.pop("storage_path", None)
    if storage_path and "storage" not in data:
        data["storage"] = {"path": str(Path(storage_path) / "memory.sqlite3")}

    if "index" in data:
        data.setdefault("metadata", {})["index"] = data.pop("index")

    if "extraction_llm" in data:
        data.setdefault("metadata", {})["extraction_llm"] = data.pop("extraction_llm")

    data.pop("backend", None)
    data.pop("package_path", None)
    return data
