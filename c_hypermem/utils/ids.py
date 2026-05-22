from __future__ import annotations

import hashlib
import json
from typing import Any

from c_hypermem.utils.text import compact_key, normalize_text


def stable_hash(*parts: Any, length: int = 16) -> str:
    payload = json.dumps(_canonical(parts), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def make_node_id(namespace: str, node_type: str, stable_key: str) -> str:
    digest = stable_hash(namespace, node_type, compact_key(stable_key))
    return f"{node_type}:{digest}"


def make_entity_id(
    namespace: str,
    canonical_name: str,
    entity_type: str = "unknown",
    disambiguators: dict[str, Any] | None = None,
) -> str:
    digest = stable_hash(namespace, compact_key(canonical_name), compact_key(entity_type), disambiguators or {})
    return f"entity:{digest}"


def make_edge_id(
    namespace: str,
    view: str,
    relation: str,
    edge_key: str,
) -> str:
    digest = stable_hash(namespace, view, relation, compact_key(edge_key))
    return f"edge:{view}:{digest}"


def make_member_signature(member_ids: list[str], roles: dict[str, str] | None = None) -> str:
    role_items = sorted((roles or {}).items())
    digest = stable_hash(sorted(member_ids), role_items, length=64)
    return f"sha256:{digest}"


def make_triple_id(
    namespace: str,
    owner_node_id: str,
    subject: str,
    predicate: str,
    object_: str,
    qualifiers: dict[str, Any] | None = None,
) -> str:
    digest = stable_hash(
        namespace,
        owner_node_id,
        normalize_text(subject),
        normalize_text(predicate),
        normalize_text(object_),
        qualifiers or {},
    )
    return f"triple:{digest}"


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_canonical(item) for item in value]
    return value
