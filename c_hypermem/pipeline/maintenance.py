from __future__ import annotations

from c_hypermem.pipeline.context import AssemblyContext
from c_hypermem.schema import (
    EdgeCluster,
    EdgeClusterMember,
    ExtractedAssertion,
    FactPropertyIndexEntry,
    HyperEdge,
    MemoryNode,
)
from c_hypermem.stores.base import MemoryStore
from c_hypermem.utils.text import normalize_text
from c_hypermem.utils.time import touch_node_update, utc_now_iso


class GraphMaintenance:
    """Apply deterministic graph maintenance that does not require extra LLM calls."""

    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store

    def retire_conflicting_facts(
        self,
        *,
        property_key: str,
        new_fact: MemoryNode,
        assertion: ExtractedAssertion,
        context: AssemblyContext,
        correction_edge_builder,
    ) -> tuple[list[MemoryNode], list[HyperEdge], list[FactPropertyIndexEntry]]:
        if self.store is None:
            return [], [], []

        retired_nodes: list[MemoryNode] = []
        correction_edges: list[HyperEdge] = []
        retired_properties: list[FactPropertyIndexEntry] = []
        old_properties = self.store.find_fact_properties(context.namespace, property_key, status="active")
        if not old_properties:
            return retired_nodes, correction_edges, retired_properties

        old_fact_ids = [item.fact_node_id for item in old_properties if item.fact_node_id != new_fact.node_id]
        for old_fact in self.store.get_nodes(context.namespace, old_fact_ids):
            if not is_conflict(old_fact, assertion):
                continue
            self._retire_fact(old_fact, new_fact, assertion, context)
            retired_nodes.append(old_fact)
            correction_edges.append(correction_edge_builder(old_fact, new_fact, context))
            retired_properties.append(
                FactPropertyIndexEntry(
                    namespace=context.namespace,
                    property_key=property_key,
                    subject_node_id=old_fact.attributes.get("subject_node_id"),
                    predicate=assertion.predicate,
                    fact_node_id=old_fact.node_id,
                    status="retired",
                    updated_at=utc_now_iso(),
                )
            )
        return retired_nodes, correction_edges, retired_properties

    def apply(
        self,
        nodes: list[MemoryNode],
        edges: list[HyperEdge],
        edge_clusters: list[EdgeCluster],
        edge_cluster_members: list[EdgeClusterMember],
    ) -> tuple[list[MemoryNode], list[HyperEdge], list[EdgeCluster], list[EdgeClusterMember]]:
        return nodes, edges, edge_clusters, edge_cluster_members

    def _retire_fact(
        self,
        old_fact: MemoryNode,
        new_fact: MemoryNode,
        assertion: ExtractedAssertion,
        context: AssemblyContext,
    ) -> None:
        old_fact.status = "retired"
        old_fact.superseded_by = new_fact.node_id
        old_fact.invalidated_by = new_fact.node_id
        old_fact.status_reason = "newer conflicting fact for the same subject and predicate"
        old_fact.status_updated_at = utc_now_iso()
        if old_fact.time.world.valid_time and not old_fact.time.world.valid_time.end:
            old_fact.time.world.valid_time.end = assertion.time or context.metadata.get("date")
        touch_node_update(old_fact, context.current_turn)


def is_conflict(old_fact: MemoryNode, assertion: ExtractedAssertion) -> bool:
    old_object = normalize_text(str(old_fact.attributes.get("object", "")))
    new_object = normalize_text(assertion.object)
    if not old_object or not new_object:
        return False
    if old_object == new_object:
        return False
    predicate = normalize_text(assertion.predicate)
    multi_value_predicates = {"likes", "enjoys", "has_hobby", "knows", "visited", "uses"}
    if predicate in multi_value_predicates:
        return False
    return True
