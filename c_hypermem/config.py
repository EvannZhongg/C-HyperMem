from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from c_hypermem.errors import ConfigError


class StorageConfig(BaseModel):
    backend: str = "sqlite"
    path: str = "runs/c_hypermem/memory.sqlite3"


class OpenAICompatibleModelConfig(BaseModel):
    provider: str = "openai_compatible"
    model: str
    base_url: str | None = None
    api_key: str | None = None


class IngestionConfig(BaseModel):
    event_mode: str = "interaction"
    incremental_build: bool = False
    max_facts_per_event: int = 12
    extractor: str | None = None


class ExtractionConfig(BaseModel):
    prompt: str = "extraction/memory_extraction.md"
    output_schema: str = "minimal_memory_candidates"
    forbid_model_ids: bool = True
    forbid_confidence: bool = True
    pass_node_types_to_prompt: bool = True
    allow_unknown_node_types: bool = True


class LocalGraphPolicyConfig(BaseModel):
    enabled: bool = True
    allow_triples: bool = True
    allow_attributes: bool = True
    allow_roles: bool = True


class IndexingPolicyConfig(BaseModel):
    lexical: bool = True
    vector: bool = True
    alias_index: bool = False


class TimePolicyConfig(BaseModel):
    prefer_world_time: bool = False


class NodeTypeConfig(BaseModel):
    enabled: bool = True
    id_strategy: str = "content_hash"
    stable_key_fields: list[str] = Field(default_factory=list)
    alias_resolution: bool = False
    property_index: bool = False
    local_graph: LocalGraphPolicyConfig = Field(default_factory=LocalGraphPolicyConfig)
    indexing: IndexingPolicyConfig = Field(default_factory=IndexingPolicyConfig)
    time: TimePolicyConfig = Field(default_factory=TimePolicyConfig)


class NodeTypesConfig(BaseModel):
    default_policy: NodeTypeConfig = Field(default_factory=NodeTypeConfig)
    types: dict[str, NodeTypeConfig] = Field(default_factory=dict)


class HyperEdgesConfig(BaseModel):
    enabled: bool = True
    build_from_extraction: bool = True
    member_policy_default: str = "appendable"
    basic_edge_types: list[str] = Field(default_factory=lambda: ["evidence", "state", "correction"])


class LocalGraphConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = True
    schema_name: str = Field(default="uniform", alias="schema")
    configured_by_node_type: bool = True


class RetrievalConfig(BaseModel):
    lexical_top_n: int = 30
    vector_top_n: int = 30
    edge_top_n: int = 30
    rerank_top_n: int = 12
    use_hyperedge_expansion: bool = True
    use_temporal_filter: bool = True
    use_recency_decay: bool = True
    recency_decay_lambda: float = 0.03
    access_boost: float = 0.05


class MemoryConfig(BaseModel):
    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: OpenAICompatibleModelConfig | None = None
    embedding: OpenAICompatibleModelConfig | None = None
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    node_types: NodeTypesConfig = Field(default_factory=NodeTypesConfig)
    hyperedges: HyperEdgesConfig = Field(default_factory=HyperEdgesConfig)
    local_graph: LocalGraphConfig = Field(default_factory=LocalGraphConfig)
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
        raw = _load_includes(raw, path.parent)
        return cls.model_validate(_normalize_external_config(raw))

    def stable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"metadata"})


def _normalize_external_config(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    data.pop("include", None)
    return data


def _load_includes(raw: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    include_values = raw.get("include", [])
    if isinstance(include_values, (str, Path)):
        include_paths = [include_values]
    else:
        include_paths = list(include_values or [])

    merged: dict[str, Any] = {}
    for include_path in include_paths:
        path = (base_dir / Path(include_path)).resolve()
        if not path.exists():
            raise ConfigError(f"Included config file does not exist: {path}")
        try:
            included = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML config: {path}") from exc
        if not isinstance(included, dict):
            raise ConfigError(f"Included config must be a mapping: {path}")
        merged = _deep_merge(merged, _load_includes(included, path.parent))
    return _deep_merge(merged, dict(raw))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
