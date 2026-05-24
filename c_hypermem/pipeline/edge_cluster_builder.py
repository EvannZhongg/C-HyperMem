from __future__ import annotations

from typing import Any, Protocol

from c_hypermem.config import MemoryConfig
from c_hypermem.pipeline.context import AssemblyContext
from c_hypermem.pipeline.graph_utils import source_metadata
from c_hypermem.schema import EdgeCluster, EdgeClusterMember, EdgeDescriptionVariant, HyperEdge
from c_hypermem.utils.ids import make_cluster_id, make_fingerprint
from c_hypermem.utils.text import compact_key


class EdgeClusterBuilder(Protocol):
    """Builds related EdgeClusters without forcing HyperEdge merges."""

    def build(
        self,
        edges: list[HyperEdge],
        *,
        namespace: str,
        metadata: dict[str, Any],
        current_turn: int,
    ) -> tuple[list[EdgeCluster], list[EdgeClusterMember]]: ...


class BasicEdgeClusterBuilder:
    """Build M1 EdgeClusters from concrete HyperEdges."""

    def __init__(self, config: MemoryConfig) -> None:
        self.config = config

    def build(
        self,
        edges: list[HyperEdge],
        *,
        namespace: str,
        metadata: dict[str, Any],
        current_turn: int,
    ) -> tuple[list[EdgeCluster], list[EdgeClusterMember]]:
        context = AssemblyContext(namespace=namespace, metadata=metadata, current_turn=current_turn)
        clusters: list[EdgeCluster] = []
        members: list[EdgeClusterMember] = []
        for edge in edges:
            cluster, member = self.build_for_edge(edge, context)
            clusters.append(cluster)
            members.append(member)
        return clusters, members

    def build_for_edge(self, edge: HyperEdge, context: AssemblyContext) -> tuple[EdgeCluster, EdgeClusterMember]:
        label = edge_cluster_label(edge)
        cluster_description = cluster_description_for_edge(edge)
        cluster_fingerprint = make_fingerprint(cluster_description, {"cluster_label": label})
        cluster = EdgeCluster(
            cluster_id=make_cluster_id(context.namespace, cluster_fingerprint),
            namespace=context.namespace,
            cluster_fingerprint=cluster_fingerprint,
            canonical_description=cluster_description,
            cluster_labels=[label],
            aliases=[compact_key(cluster_description)] if compact_key(cluster_description) else [],
            conflict_state="contains_conflict" if edge.edge_type == "correction" else "none",
            description_variants=[EdgeDescriptionVariant(text=edge.description, source_edge_id=edge.edge_id)],
            metadata=source_metadata(context, source_ref=edge.edge_type),
        )
        member = EdgeClusterMember(
            namespace=context.namespace,
            cluster_id=cluster.cluster_id,
            edge_id=edge.edge_id,
            relation_to_cluster="updates" if edge.edge_type == "correction" else "supports",
        )
        return cluster, member


def edge_cluster_label(edge: HyperEdge) -> str:
    if edge.edge_type == "state":
        return "entity_state"
    if edge.edge_type == "correction":
        return "conflict_resolution"
    return f"{edge.edge_type}_context"


def cluster_description_for_edge(edge: HyperEdge) -> str:
    if edge.edge_type == "state":
        return edge.description
    return f"{edge.edge_type}: {edge.relation}"
