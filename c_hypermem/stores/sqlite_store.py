from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from c_hypermem.errors import StoreError
from c_hypermem.schema import (
    EntityAliasIndexEntry,
    FactPropertyIndexEntry,
    HyperEdge,
    LocalNodeGraph,
    MemoryNode,
    TimeBundle,
)
from c_hypermem.utils.ids import make_member_signature
from c_hypermem.utils.time import utc_now_iso


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def reset_namespace(self, namespace: str) -> None:
        with self.conn:
            for table in [
                "triples",
                "hyper_edge_members",
                "hyper_edges",
                "nodes",
                "fact_property_index",
                "entity_alias_index",
                "ingestion_cache",
            ]:
                self.conn.execute(f"DELETE FROM {table} WHERE namespace = ?", (namespace,))

    def upsert_nodes(self, nodes: list[MemoryNode]) -> None:
        with self.conn:
            for node in nodes:
                self.conn.execute(
                    """
                    INSERT INTO nodes (
                        namespace, node_id, node_type, status, superseded_by,
                        invalidated_by, status_reason, status_updated_at, content, summary,
                        attributes_json, absolute_time_json, relative_time_json,
                        local_graph_json, metadata_json, dedupe_key
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, node_id) DO UPDATE SET
                        node_type = excluded.node_type,
                        status = excluded.status,
                        superseded_by = excluded.superseded_by,
                        invalidated_by = excluded.invalidated_by,
                        status_reason = excluded.status_reason,
                        status_updated_at = excluded.status_updated_at,
                        content = excluded.content,
                        summary = excluded.summary,
                        attributes_json = excluded.attributes_json,
                        absolute_time_json = excluded.absolute_time_json,
                        relative_time_json = excluded.relative_time_json,
                        local_graph_json = excluded.local_graph_json,
                        metadata_json = excluded.metadata_json,
                        dedupe_key = excluded.dedupe_key
                    """,
                    (
                        node.namespace,
                        node.id,
                        node.type,
                        node.status,
                        node.superseded_by,
                        node.invalidated_by,
                        node.status_reason,
                        node.status_updated_at,
                        node.content,
                        node.summary,
                        _to_json(node.attributes),
                        _to_json(node.time.world),
                        _to_json(
                            {
                                "lifecycle": node.time.lifecycle.model_dump(mode="json"),
                                "activation": node.time.activation.model_dump(mode="json"),
                            }
                        ),
                        _to_json(node.local_graph),
                        _to_json(node.metadata),
                        node.dedupe_key,
                    ),
                )
                self.conn.execute(
                    "DELETE FROM triples WHERE namespace = ? AND owner_node_id = ?",
                    (node.namespace, node.id),
                )
                for triple in node.local_graph.triples:
                    self.conn.execute(
                        """
                        INSERT INTO triples (
                            namespace, triple_id, owner_node_id, subject, predicate, object,
                            status, superseded_by, invalidated_by, qualifiers_json, metadata_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(namespace, triple_id) DO UPDATE SET
                            owner_node_id = excluded.owner_node_id,
                            subject = excluded.subject,
                            predicate = excluded.predicate,
                            object = excluded.object,
                            status = excluded.status,
                            superseded_by = excluded.superseded_by,
                            invalidated_by = excluded.invalidated_by,
                            qualifiers_json = excluded.qualifiers_json,
                            metadata_json = excluded.metadata_json
                        """,
                        (
                            node.namespace,
                            triple.id or "",
                            node.id,
                            triple.subject,
                            triple.predicate,
                            triple.object,
                            triple.status,
                            triple.superseded_by,
                            triple.invalidated_by,
                            _to_json(triple.qualifiers),
                            _to_json({}),
                        ),
                    )

    def upsert_edges(self, edges: list[HyperEdge]) -> None:
        with self.conn:
            for edge in edges:
                if not edge.member_signature:
                    edge.member_signature = make_member_signature(edge.node_ids, edge.roles)
                self.conn.execute(
                    """
                    INSERT INTO hyper_edges (
                        namespace, edge_id, edge_type, relation, edge_key, member_policy,
                        member_signature, member_version, absolute_time_json, relative_time_json, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, edge_id) DO UPDATE SET
                        edge_type = excluded.edge_type,
                        relation = excluded.relation,
                        edge_key = excluded.edge_key,
                        member_policy = excluded.member_policy,
                        member_signature = excluded.member_signature,
                        member_version = excluded.member_version,
                        absolute_time_json = excluded.absolute_time_json,
                        relative_time_json = excluded.relative_time_json,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        edge.namespace,
                        edge.id,
                        edge.edge_type,
                        edge.relation,
                        edge.edge_key,
                        edge.member_policy,
                        edge.member_signature,
                        edge.member_version,
                        _to_json(edge.time.world),
                        _to_json(
                            {
                                "lifecycle": edge.time.lifecycle.model_dump(mode="json"),
                                "activation": edge.time.activation.model_dump(mode="json"),
                            }
                        ),
                        _to_json(edge.metadata),
                    ),
                )
                self.conn.execute(
                    "DELETE FROM hyper_edge_members WHERE namespace = ? AND edge_id = ?",
                    (edge.namespace, edge.id),
                )
                for node_id in edge.node_ids:
                    self.conn.execute(
                        """
                        INSERT INTO hyper_edge_members (namespace, edge_id, node_id, role, weight)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            edge.namespace,
                            edge.id,
                            node_id,
                            edge.roles.get(node_id),
                            edge.weights.get(node_id, 1.0),
                        ),
                    )

    def upsert_entity_aliases(self, aliases: list[EntityAliasIndexEntry]) -> None:
        with self.conn:
            for alias in aliases:
                self.conn.execute(
                    """
                    INSERT INTO entity_alias_index (
                        namespace, normalized_alias, entity_type, entity_id, source_count, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, normalized_alias, entity_type) DO UPDATE SET
                        entity_id = excluded.entity_id,
                        source_count = entity_alias_index.source_count + excluded.source_count,
                        updated_at = excluded.updated_at
                    """,
                    (
                        alias.namespace,
                        alias.normalized_alias,
                        alias.entity_type or "",
                        alias.entity_id,
                        alias.source_count,
                        alias.updated_at or utc_now_iso(),
                    ),
                )

    def find_entity_alias(
        self,
        namespace: str,
        normalized_aliases: list[str],
        entity_type: str | None = None,
    ) -> EntityAliasIndexEntry | None:
        if not normalized_aliases:
            return None
        placeholders = ",".join("?" for _ in normalized_aliases)
        params: list[Any] = [namespace, *normalized_aliases]
        type_filter = ""
        if entity_type is not None:
            type_filter = "AND entity_type IN (?, '')"
            params.append(entity_type)
        row = self.conn.execute(
            f"""
            SELECT *
            FROM entity_alias_index
            WHERE namespace = ? AND normalized_alias IN ({placeholders}) {type_filter}
            ORDER BY source_count DESC, updated_at DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if not row:
            return None
        return EntityAliasIndexEntry(
            namespace=row["namespace"],
            normalized_alias=row["normalized_alias"],
            entity_type=row["entity_type"] or None,
            entity_id=row["entity_id"],
            source_count=int(row["source_count"]),
            updated_at=row["updated_at"],
        )

    def upsert_fact_properties(self, properties: list[FactPropertyIndexEntry]) -> None:
        with self.conn:
            for item in properties:
                self.conn.execute(
                    """
                    INSERT INTO fact_property_index (
                        namespace, property_key, entity_id, predicate, fact_id, status, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, property_key, fact_id) DO UPDATE SET
                        entity_id = excluded.entity_id,
                        predicate = excluded.predicate,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item.namespace,
                        item.property_key,
                        item.entity_id,
                        item.predicate,
                        item.fact_id,
                        item.status,
                        item.updated_at or utc_now_iso(),
                    ),
                )

    def find_fact_properties(
        self,
        namespace: str,
        property_key: str,
        status: str | None = "active",
    ) -> list[FactPropertyIndexEntry]:
        params: list[Any] = [namespace, property_key]
        status_filter = ""
        if status is not None:
            status_filter = "AND status = ?"
            params.append(status)
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM fact_property_index
            WHERE namespace = ? AND property_key = ? {status_filter}
            ORDER BY updated_at DESC
            """,
            params,
        ).fetchall()
        return [
            FactPropertyIndexEntry(
                namespace=row["namespace"],
                property_key=row["property_key"],
                entity_id=row["entity_id"],
                predicate=row["predicate"],
                fact_id=row["fact_id"],
                status=row["status"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def list_nodes(self, namespace: str) -> list[MemoryNode]:
        rows = self.conn.execute(
            "SELECT * FROM nodes WHERE namespace = ? ORDER BY rowid",
            (namespace,),
        ).fetchall()
        return [_node_from_row(row) for row in rows]

    def list_edges(self, namespace: str) -> list[HyperEdge]:
        rows = self.conn.execute(
            "SELECT * FROM hyper_edges WHERE namespace = ? ORDER BY rowid",
            (namespace,),
        ).fetchall()
        return [_edge_from_row(row, _edge_members(self.conn, row["namespace"], row["edge_id"])) for row in rows]

    def get_nodes(self, namespace: str, node_ids: list[str]) -> list[MemoryNode]:
        if not node_ids:
            return []
        placeholders = ",".join("?" for _ in node_ids)
        rows = self.conn.execute(
            f"SELECT * FROM nodes WHERE namespace = ? AND node_id IN ({placeholders})",
            [namespace, *node_ids],
        ).fetchall()
        by_id = {_node_from_row(row).id: _node_from_row(row) for row in rows}
        return [by_id[node_id] for node_id in node_ids if node_id in by_id]

    def get_incident_edges(self, namespace: str, node_ids: list[str]) -> list[HyperEdge]:
        if not node_ids:
            return []
        placeholders = ",".join("?" for _ in node_ids)
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT ve.*
            FROM hyper_edges ve
            JOIN hyper_edge_members vem
              ON ve.namespace = vem.namespace AND ve.edge_id = vem.edge_id
            WHERE vem.namespace = ? AND vem.node_id IN ({placeholders})
            ORDER BY ve.rowid
            """,
            [namespace, *node_ids],
        ).fetchall()
        return [_edge_from_row(row, _edge_members(self.conn, row["namespace"], row["edge_id"])) for row in rows]

    def stats(self, namespace: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for key, table in {
            "nodes": "nodes",
            "hyper_edges": "hyper_edges",
            "triples": "triples",
            "fact_properties": "fact_property_index",
            "entity_aliases": "entity_alias_index",
        }.items():
            row = self.conn.execute(
                f"SELECT COUNT(*) AS count FROM {table} WHERE namespace = ?",
                (namespace,),
            ).fetchone()
            result[key] = int(row["count"])

        for row in self.conn.execute(
            """
            SELECT node_type, COUNT(*) AS count
            FROM nodes
            WHERE namespace = ?
            GROUP BY node_type
            """,
            (namespace,),
        ).fetchall():
            result[f"nodes.{row['node_type']}"] = int(row["count"])
        return result

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        try:
            with self.conn:
                self.conn.executescript(
                    """
                    PRAGMA journal_mode = WAL;

                    CREATE TABLE IF NOT EXISTS nodes (
                        namespace TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        node_type TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        superseded_by TEXT,
                        invalidated_by TEXT,
                        status_reason TEXT,
                        status_updated_at TEXT,
                        content TEXT NOT NULL,
                        summary TEXT NOT NULL DEFAULT '',
                        attributes_json TEXT NOT NULL,
                        absolute_time_json TEXT NOT NULL,
                        relative_time_json TEXT NOT NULL,
                        local_graph_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        dedupe_key TEXT,
                        PRIMARY KEY (namespace, node_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_nodes_namespace_type
                        ON nodes(namespace, node_type);

                    CREATE INDEX IF NOT EXISTS idx_nodes_namespace_dedupe
                        ON nodes(namespace, dedupe_key);

                    CREATE TABLE IF NOT EXISTS hyper_edges (
                        namespace TEXT NOT NULL,
                        edge_id TEXT NOT NULL,
                        edge_type TEXT NOT NULL,
                        relation TEXT NOT NULL,
                        edge_key TEXT NOT NULL DEFAULT '',
                        member_policy TEXT NOT NULL DEFAULT 'immutable',
                        member_signature TEXT NOT NULL DEFAULT '',
                        member_version INTEGER NOT NULL DEFAULT 1,
                        absolute_time_json TEXT NOT NULL,
                        relative_time_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        PRIMARY KEY (namespace, edge_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_hyper_edges_namespace_type
                        ON hyper_edges(namespace, edge_type);

                    CREATE TABLE IF NOT EXISTS hyper_edge_members (
                        namespace TEXT NOT NULL,
                        edge_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        role TEXT,
                        weight REAL NOT NULL DEFAULT 1.0
                    );

                    CREATE INDEX IF NOT EXISTS idx_hyper_edge_members_node
                        ON hyper_edge_members(namespace, node_id);

                    CREATE TABLE IF NOT EXISTS triples (
                        namespace TEXT NOT NULL,
                        triple_id TEXT NOT NULL,
                        owner_node_id TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        object TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        superseded_by TEXT,
                        invalidated_by TEXT,
                        qualifiers_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        PRIMARY KEY (namespace, triple_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_triples_owner
                        ON triples(namespace, owner_node_id);

                    CREATE TABLE IF NOT EXISTS fact_property_index (
                        namespace TEXT NOT NULL,
                        property_key TEXT NOT NULL,
                        entity_id TEXT,
                        predicate TEXT NOT NULL,
                        fact_id TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (namespace, property_key, fact_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fact_property_lookup
                        ON fact_property_index(namespace, property_key, status);

                    CREATE TABLE IF NOT EXISTS entity_alias_index (
                        namespace TEXT NOT NULL,
                        normalized_alias TEXT NOT NULL,
                        entity_type TEXT NOT NULL DEFAULT '',
                        entity_id TEXT NOT NULL,
                        source_count INTEGER NOT NULL DEFAULT 1,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (namespace, normalized_alias, entity_type)
                    );

                    CREATE INDEX IF NOT EXISTS idx_entity_alias_lookup
                        ON entity_alias_index(namespace, normalized_alias, entity_type);

                    CREATE TABLE IF NOT EXISTS ingestion_cache (
                        namespace TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        system_prompt_hash TEXT,
                        memory_config_hash TEXT,
                        prompt_template_hash TEXT,
                        processed_prefix_hash TEXT,
                        last_processed_turn_index INTEGER,
                        last_processed_message_id TEXT,
                        last_event_id TEXT,
                        metadata_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (namespace, conversation_id)
                    );
                    """
                )
        except sqlite3.DatabaseError as exc:
            raise StoreError(f"Failed to initialize SQLite store: {self.path}") from exc


def _to_json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _from_json(value: str, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _node_from_row(row: sqlite3.Row) -> MemoryNode:
    return MemoryNode(
        id=row["node_id"],
        namespace=row["namespace"],
        type=row["node_type"],
        status=row["status"],
        superseded_by=row["superseded_by"],
        invalidated_by=row["invalidated_by"],
        status_reason=row["status_reason"],
        status_updated_at=row["status_updated_at"],
        content=row["content"],
        summary=row["summary"],
        attributes=_from_json(row["attributes_json"], {}),
        time=_time_from_columns(row["absolute_time_json"], row["relative_time_json"]),
        local_graph=LocalNodeGraph.model_validate(_from_json(row["local_graph_json"], {})),
        metadata=_from_json(row["metadata_json"], {}),
        dedupe_key=row["dedupe_key"],
    )


def _edge_from_row(row: sqlite3.Row, members: list[sqlite3.Row]) -> HyperEdge:
    node_ids = [member["node_id"] for member in members]
    roles = {member["node_id"]: member["role"] for member in members if member["role"] is not None}
    weights = {member["node_id"]: float(member["weight"]) for member in members}
    return HyperEdge(
        id=row["edge_id"],
        namespace=row["namespace"],
        edge_type=row["edge_type"],
        relation=row["relation"],
        edge_key=row["edge_key"],
        member_policy=row["member_policy"],
        member_signature=row["member_signature"],
        member_version=int(row["member_version"]),
        node_ids=node_ids,
        roles=roles,
        weights=weights,
        time=_time_from_columns(row["absolute_time_json"], row["relative_time_json"]),
        metadata=_from_json(row["metadata_json"], {}),
    )


def _edge_members(conn: sqlite3.Connection, namespace: str, edge_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT node_id, role, weight
        FROM hyper_edge_members
        WHERE namespace = ? AND edge_id = ?
        ORDER BY rowid
        """,
        (namespace, edge_id),
    ).fetchall()


def _time_from_columns(absolute_time_json: str, relative_time_json: str) -> TimeBundle:
    time = TimeBundle()
    time.world = time.world.model_validate(_from_json(absolute_time_json, {}))
    relative_time = _from_json(relative_time_json, {})
    time.lifecycle = time.lifecycle.model_validate(relative_time.get("lifecycle", {}))
    time.activation = time.activation.model_validate(relative_time.get("activation", {}))
    return time
