from __future__ import annotations

from c_hypermem.config import NLPConfig, RetrievalConfig
from c_hypermem.embeddings import EmbeddingClient
from c_hypermem.llms.base import LLMClient
from c_hypermem.retrieval.fusion import FusedNode, RankedNodeList, reciprocal_rank_fusion_channels
from c_hypermem.retrieval.graph_ripple import GraphRippleExpansion, RankedEdge
from c_hypermem.retrieval.lexical_recall import SQLiteFTSRecall
from c_hypermem.retrieval.query_analysis import build_query_analyzer
from c_hypermem.retrieval.vector_recall import DenseVectorRecall, VectorEdgeHit
from c_hypermem.schema import HyperEdge, MemoryNode, SearchResult
from c_hypermem.stores.base import MemoryStore
from c_hypermem.stores.vector_store import VectorStore


class Retriever:
    def __init__(
        self,
        store: MemoryStore,
        config: RetrievalConfig,
        *,
        nlp_config: NLPConfig | None = None,
        query_analysis_llm: LLMClient | None = None,
        embedding_client: EmbeddingClient | None = None,
        vector_stores: dict[str, VectorStore] | None = None,
    ) -> None:
        self.store = store
        self.config = config
        self.analyzer = build_query_analyzer(config, nlp_config=nlp_config, llm=query_analysis_llm)
        self.lexical_recall = SQLiteFTSRecall(store, config)
        self.vector_recall = DenseVectorRecall(
            store,
            config,
            embedding_client=embedding_client,
            vector_stores=vector_stores,
        )
        self.graph_ripple = GraphRippleExpansion(store, config)

    def search(
        self,
        query: str,
        *,
        namespace: str,
        top_k: int,
        current_turn: int | None = None,
    ) -> list[SearchResult]:
        analysis = self.analyzer.analyze(query)
        query_vector = self.vector_recall.embed_query(analysis.query)
        lexical_hits = self.lexical_recall.recall(namespace=namespace, query=analysis.query)
        vector_hits = self.vector_recall.recall(
            namespace=namespace,
            query=analysis.query,
            query_vector=query_vector,
        )
        edge_hits = self.vector_recall.recall_hyper_edges(
            namespace=namespace,
            query=analysis.query,
            query_vector=query_vector,
        )

        vector_node_ids = list(dict.fromkeys(hit.node_id for hit in vector_hits))
        vector_nodes = self.store.get_nodes(namespace, vector_node_ids)
        vector_nodes_by_id = {node.node_id: node for node in vector_nodes}
        vector_hits_by_node: dict[str, list[dict[str, object]]] = {}
        best_vector_score_by_channel: dict[str, dict[str, float]] = {}
        for hit in vector_hits:
            channel_scores = best_vector_score_by_channel.setdefault(hit.channel, {})
            channel_scores[hit.node_id] = max(channel_scores.get(hit.node_id, float("-inf")), hit.score)
            vector_hits_by_node.setdefault(hit.node_id, []).append(
                {
                    "channel": hit.channel,
                    "score": hit.score,
                    "id": hit.hit.id,
                    "text": hit.hit.text,
                    "payload": hit.hit.payload,
                }
            )

        ranked_lists = [
            RankedNodeList(
                nodes=[hit.node for hit in lexical_hits],
                channel="lexical",
                score_key="rrf_lexical",
            )
        ]
        for channel in ("node_content", "node_local_graph"):
            scores = best_vector_score_by_channel.get(channel, {})
            channel_nodes = sorted(
                [vector_nodes_by_id[node_id] for node_id in vector_node_ids if node_id in vector_nodes_by_id and node_id in scores],
                key=lambda node: scores.get(node.node_id, float("-inf")),
                reverse=True,
            )
            ranked_lists.append(
                RankedNodeList(
                    nodes=channel_nodes,
                    channel=channel,
                    score_key=f"rrf_{channel}",
                )
            )

        fused = reciprocal_rank_fusion_channels(
            ranked_lists=ranked_lists,
            vector_hit_payloads=vector_hits_by_node,
            k=max(1, self.config.rrf_k),
        )
        node_ranked_edges = self.graph_ripple.expand(namespace=namespace, initial=fused)
        description_ranked_edges = self._rank_description_hit_edges(namespace, edge_hits)
        ranked_edges = self._merge_ranked_edges(node_ranked_edges, description_ranked_edges)

        limit = min(top_k, self.config.final_top_k)
        return [self._to_result(item, analysis_metadata=analysis.to_metadata()) for item in ranked_edges[:limit]]

    def _rank_description_hit_edges(self, namespace: str, edge_hits: list[VectorEdgeHit]) -> list[RankedEdge]:
        if not edge_hits:
            return []
        edges = self.store.get_edges(namespace, list(dict.fromkeys(hit.edge_id for hit in edge_hits)))
        edges_by_id = {edge.edge_id: edge for edge in edges if edge.status == "active"}
        nodes_by_id = self._nodes_for_edges(namespace, edges_by_id.values())

        ranked: list[RankedEdge] = []
        seen_edge_ids: set[str] = set()
        for rank, hit in enumerate(edge_hits, start=1):
            edge = edges_by_id.get(hit.edge_id)
            if edge is None or edge.edge_id in seen_edge_ids:
                continue
            seen_edge_ids.add(edge.edge_id)
            score = 1.0 / (max(1, self.config.rrf_k) + rank)
            nodes = [
                FusedNode(
                    node=node,
                    score=score,
                    channels={"hyper_edge_description_vector"},
                    score_parts={"rrf_hyper_edge_description_vector": score},
                    vector_hits=[
                        {
                            "channel": hit.channel,
                            "score": hit.score,
                            "id": hit.hit.id,
                            "text": hit.hit.text,
                            "payload": hit.hit.payload,
                        }
                    ],
                    edge_ids={edge.edge_id},
                    cluster_ids=set(),
                )
                for node_id in edge.node_ids
                if (node := nodes_by_id.get(node_id)) is not None and node.status == "active"
            ]
            if not nodes:
                continue
            ranked.append(
                RankedEdge(
                    edge=edge,
                    score=score,
                    nodes=nodes,
                    score_parts={
                        "hyper_edge_description_vector": score,
                        "rrf_hyper_edge_description_vector": score,
                    },
                    cluster_ids=set(),
                    cluster_edge_descriptions=[],
                    hit_node_ids=set(),
                )
            )
        return ranked

    def _nodes_for_edges(self, namespace: str, edges) -> dict[str, MemoryNode]:
        node_ids: list[str] = []
        for edge in edges:
            node_ids.extend(edge.node_ids)
        return {
            node.node_id: node
            for node in self.store.get_nodes(namespace, list(dict.fromkeys(node_ids)))
        }

    def _merge_ranked_edges(
        self,
        node_ranked_edges: list[RankedEdge],
        description_ranked_edges: list[RankedEdge],
    ) -> list[RankedEdge]:
        merged: dict[str, RankedEdge] = {}
        for item in [*node_ranked_edges, *description_ranked_edges]:
            existing = merged.get(item.edge.edge_id)
            if existing is None:
                merged[item.edge.edge_id] = item
                continue
            existing.score = max(existing.score, item.score)
            existing.score_parts = {**existing.score_parts, **item.score_parts}
            existing.cluster_ids.update(item.cluster_ids)
            existing.hit_node_ids.update(item.hit_node_ids)
            existing.cluster_edge_descriptions = _unique_edge_description_payloads(
                [*existing.cluster_edge_descriptions, *item.cluster_edge_descriptions]
            )
            existing.nodes = _merge_fused_nodes(existing.nodes, item.nodes)
        return sorted(merged.values(), key=lambda item: item.score, reverse=True)

    def _to_result(self, ranked_edge: RankedEdge, *, analysis_metadata: dict) -> SearchResult:
        edge = ranked_edge.edge
        metadata = {
            "query_analysis": analysis_metadata,
            "edge_id": edge.edge_id,
            "hyper_edge_ids": [edge.edge_id],
            "edge_description": edge.description,
            "edge_node_ids": edge.node_ids,
            "channels": sorted({channel for node in ranked_edge.nodes for channel in node.channels}),
            "hit_node_ids": sorted(ranked_edge.hit_node_ids),
            "cluster_ids": sorted(ranked_edge.cluster_ids),
            "cluster_edge_descriptions": ranked_edge.cluster_edge_descriptions,
            "score_parts": ranked_edge.score_parts,
            "time": edge.time.model_dump(mode="json"),
            "edge_metadata": edge.metadata,
            "edge_nodes": [self._node_metadata(item) for item in ranked_edge.nodes],
        }
        return SearchResult(
            id=edge.edge_id,
            content=self._edge_content(ranked_edge),
            score=float(ranked_edge.score),
            metadata=metadata,
        )

    def _node_metadata(self, fused: FusedNode) -> dict[str, object]:
        node = fused.node
        payload: dict[str, object] = {
            "node_id": node.node_id,
            "node_labels": node.node_labels,
            "content": node.content,
            "summary": node.summary,
            "score": fused.score,
            "channels": sorted(fused.channels),
            "score_parts": fused.score_parts,
            "matched_vector_items": fused.vector_hits,
            "source_turn_ids": node.metadata.get("source_turn_ids", []),
            "time": node.time.model_dump(mode="json"),
            "node_metadata": node.metadata,
            "triples": [
                triple.model_dump(mode="json")
                for triple in node.local_graph.triples
                if triple.status == "active"
            ],
        }
        return payload

    def _edge_content(self, ranked_edge: RankedEdge) -> str:
        edge = ranked_edge.edge
        node_lines = "\n".join(f"- {item.node.content}" for item in ranked_edge.nodes)
        return f"{edge.description}\nNodes:\n{node_lines}"


def _merge_fused_nodes(left: list[FusedNode], right: list[FusedNode]) -> list[FusedNode]:
    merged: dict[str, FusedNode] = {item.node.node_id: item for item in left}
    for item in right:
        existing = merged.get(item.node.node_id)
        if existing is None:
            merged[item.node.node_id] = item
            continue
        existing.score = max(existing.score, item.score)
        existing.channels.update(item.channels)
        existing.score_parts = {**existing.score_parts, **item.score_parts}
        existing.vector_hits = _unique_vector_hits([*existing.vector_hits, *item.vector_hits])
        existing.edge_ids.update(item.edge_ids)
        existing.cluster_ids.update(item.cluster_ids)
    return sorted(merged.values(), key=lambda node: node.score, reverse=True)


def _unique_vector_hits(items: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[object, object]] = set()
    unique: list[dict[str, object]] = []
    for item in items:
        key = (item.get("channel"), item.get("id"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _unique_edge_description_payloads(items: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[object, object, object]] = set()
    unique: list[dict[str, object]] = []
    for item in items:
        key = (item.get("cluster_id"), item.get("edge_id"), item.get("description"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
