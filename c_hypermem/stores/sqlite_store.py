from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from c_hypermem.errors import StoreError
from c_hypermem.schema import LocalNodeGraph, LocalTriple, SharedNode, TimeBundle, ViewEdge


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
                "view_edge_members",
                "view_edges",
                "nodes",
                "ingestion_cache",
            ]:
                self.conn.execute(f"DELETE FROM {table} WHERE namespace = ?", (namespace,))

    def upsert_nodes(self, nodes: list[SharedNode]) -> None:
        with self.conn:
            for node in nodes:
                self.conn.execute(
                    """
                    INSERT INTO nodes (
                        namespace, node_id, node_type, content, summary,
                        time_json, local_graph_json, metadata_json, dedupe_key
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, node_id) DO UPDATE SET
                        node_type = excluded.node_type,
                        content = excluded.content,
                        summary = excluded.summary,
                        time_json = excluded.time_json,
                        local_graph_json = excluded.local_graph_json,
                        metadata_json = excluded.metadata_json,
                        dedupe_key = excluded.dedupe_key
                    """,
                    (
                        node.namespace,
                        node.id,
                        node.type,
                        node.content,
                        node.summary,
                        _to_json(node.time),
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
                            namespace, triple_id, owner_node_id, subject, predicate, object, metadata_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(namespace, triple_id) DO UPDATE SET
                            owner_node_id = excluded.owner_node_id,
                            subject = excluded.subject,
                            predicate = excluded.predicate,
                            object = excluded.object,
                            metadata_json = excluded.metadata_json
                        """,
                        (
                            node.namespace,
                            triple.id or "",
                            node.id,
                            triple.subject,
                            triple.predicate,
                            triple.object,
                            _to_json(triple.qualifiers),
                        ),
                    )

    def upsert_edges(self, edges: list[ViewEdge]) -> None:
        with self.conn:
            for edge in edges:
                self.conn.execute(
                    """
                    INSERT INTO view_edges (
                        namespace, edge_id, view, relation, node_ids_json,
                        roles_json, weights_json, time_json, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, edge_id) DO UPDATE SET
                        view = excluded.view,
                        relation = excluded.relation,
                        node_ids_json = excluded.node_ids_json,
                        roles_json = excluded.roles_json,
                        weights_json = excluded.weights_json,
                        time_json = excluded.time_json,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        edge.namespace,
                        edge.id,
                        edge.view,
                        edge.relation,
                        _to_json(edge.node_ids),
                        _to_json(edge.roles),
                        _to_json(edge.weights),
                        _to_json(edge.time),
                        _to_json(edge.metadata),
                    ),
                )
                self.conn.execute(
                    "DELETE FROM view_edge_members WHERE namespace = ? AND edge_id = ?",
                    (edge.namespace, edge.id),
                )
                for node_id in edge.node_ids:
                    self.conn.execute(
                        """
                        INSERT INTO view_edge_members (namespace, edge_id, node_id, role, weight)
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

    def list_nodes(self, namespace: str) -> list[SharedNode]:
        rows = self.conn.execute(
            "SELECT * FROM nodes WHERE namespace = ? ORDER BY rowid",
            (namespace,),
        ).fetchall()
        return [_node_from_row(row) for row in rows]

    def list_edges(self, namespace: str) -> list[ViewEdge]:
        rows = self.conn.execute(
            "SELECT * FROM view_edges WHERE namespace = ? ORDER BY rowid",
            (namespace,),
        ).fetchall()
        return [_edge_from_row(row) for row in rows]

    def get_nodes(self, namespace: str, node_ids: list[str]) -> list[SharedNode]:
        if not node_ids:
            return []
        placeholders = ",".join("?" for _ in node_ids)
        rows = self.conn.execute(
            f"SELECT * FROM nodes WHERE namespace = ? AND node_id IN ({placeholders})",
            [namespace, *node_ids],
        ).fetchall()
        by_id = {_node_from_row(row).id: _node_from_row(row) for row in rows}
        return [by_id[node_id] for node_id in node_ids if node_id in by_id]

    def get_incident_edges(self, namespace: str, node_ids: list[str]) -> list[ViewEdge]:
        if not node_ids:
            return []
        placeholders = ",".join("?" for _ in node_ids)
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT ve.*
            FROM view_edges ve
            JOIN view_edge_members vem
              ON ve.namespace = vem.namespace AND ve.edge_id = vem.edge_id
            WHERE vem.namespace = ? AND vem.node_id IN ({placeholders})
            ORDER BY ve.rowid
            """,
            [namespace, *node_ids],
        ).fetchall()
        return [_edge_from_row(row) for row in rows]

    def stats(self, namespace: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for key, table in {
            "nodes": "nodes",
            "edges": "view_edges",
            "triples": "triples",
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
                        content TEXT NOT NULL,
                        summary TEXT NOT NULL DEFAULT '',
                        time_json TEXT NOT NULL,
                        local_graph_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        dedupe_key TEXT,
                        PRIMARY KEY (namespace, node_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_nodes_namespace_type
                        ON nodes(namespace, node_type);

                    CREATE INDEX IF NOT EXISTS idx_nodes_namespace_dedupe
                        ON nodes(namespace, dedupe_key);

                    CREATE TABLE IF NOT EXISTS view_edges (
                        namespace TEXT NOT NULL,
                        edge_id TEXT NOT NULL,
                        view TEXT NOT NULL,
                        relation TEXT NOT NULL,
                        node_ids_json TEXT NOT NULL,
                        roles_json TEXT NOT NULL,
                        weights_json TEXT NOT NULL,
                        time_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        PRIMARY KEY (namespace, edge_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_edges_namespace_view
                        ON view_edges(namespace, view);

                    CREATE TABLE IF NOT EXISTS view_edge_members (
                        namespace TEXT NOT NULL,
                        edge_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        role TEXT,
                        weight REAL NOT NULL DEFAULT 1.0
                    );

                    CREATE INDEX IF NOT EXISTS idx_edge_members_node
                        ON view_edge_members(namespace, node_id);

                    CREATE TABLE IF NOT EXISTS triples (
                        namespace TEXT NOT NULL,
                        triple_id TEXT NOT NULL,
                        owner_node_id TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        object TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        PRIMARY KEY (namespace, triple_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_triples_owner
                        ON triples(namespace, owner_node_id);

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


def _node_from_row(row: sqlite3.Row) -> SharedNode:
    return SharedNode(
        id=row["node_id"],
        namespace=row["namespace"],
        type=row["node_type"],
        content=row["content"],
        summary=row["summary"],
        time=TimeBundle.model_validate(_from_json(row["time_json"], {})),
        local_graph=LocalNodeGraph.model_validate(_from_json(row["local_graph_json"], {})),
        metadata=_from_json(row["metadata_json"], {}),
        dedupe_key=row["dedupe_key"],
    )


def _edge_from_row(row: sqlite3.Row) -> ViewEdge:
    return ViewEdge(
        id=row["edge_id"],
        namespace=row["namespace"],
        view=row["view"],
        relation=row["relation"],
        node_ids=_from_json(row["node_ids_json"], []),
        roles=_from_json(row["roles_json"], {}),
        weights=_from_json(row["weights_json"], {}),
        time=TimeBundle.model_validate(_from_json(row["time_json"], {})),
        metadata=_from_json(row["metadata_json"], {}),
    )

