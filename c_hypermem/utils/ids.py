from __future__ import annotations

from typing import Any

from c_hypermem.utils.hashing import stable_hash
from c_hypermem.utils.text import compact_key, normalize_text


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
    edge_type: str,
    relation: str,
    edge_key: str,
) -> str:
    digest = stable_hash(namespace, edge_type, relation, compact_key(edge_key))
    return f"edge:{edge_type}:{digest}"


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
