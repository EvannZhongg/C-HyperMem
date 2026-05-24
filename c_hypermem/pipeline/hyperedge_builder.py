from __future__ import annotations

from typing import Any, Protocol

from c_hypermem.config import MemoryConfig
from c_hypermem.pipeline.context import AssemblyContext
from c_hypermem.pipeline.graph_utils import source_metadata
from c_hypermem.schema import HyperEdge, MemoryNode
from c_hypermem.utils.ids import make_edge_id, make_fingerprint, make_member_signature
from c_hypermem.utils.time import make_time_bundle


class HyperEdgeBuilder(Protocol):
    """Builds or updates HyperEdges from extracted memory nodes."""

    def build(
        self,
        nodes: list[MemoryNode],
        *,
        namespace: str,
        metadata: dict[str, Any],
        current_turn: int,
    ) -> list[HyperEdge]: ...


class BasicHyperEdgeBuilder:
    """Build deterministic M1 HyperEdges from system-assembled nodes."""

    def __init__(self, config: MemoryConfig) -> None:
        self.config = config

    def build(
        self,
        nodes: list[MemoryNode],
        *,
        namespace: str,
        metadata: dict[str, Any],
        current_turn: int,
    ) -> list[HyperEdge]:
        return []

    def build_evidence_edge(
        self,
        event_node: MemoryNode,
        fact_nodes: list[MemoryNode],
        context: AssemblyContext,
    ) -> HyperEdge:
        node_ids = [event_node.node_id, *[fact.node_id for fact in fact_nodes]]
        roles = {event_node.node_id: "evidence_event", **{fact.node_id: "derived_fact" for fact in fact_nodes}}
        description = f"{event_node.summary} supports {len(fact_nodes)} extracted fact(s)."
        edge = self._edge(
            edge_type="evidence",
            relation="supports_extracted_facts",
            description=description,
            node_ids=node_ids,
            roles=roles,
            context=context,
        )
        for fact in fact_nodes:
            self.attach_fact_triples_to_edge(fact, edge, roles.get(fact.node_id))
        return edge

    def build_state_edge(
        self,
        subject_node: MemoryNode,
        fact_node: MemoryNode,
        *,
        subject: str,
        predicate: str,
        object_: str,
        polarity: str,
        event_node: MemoryNode | None,
        context: AssemblyContext,
    ) -> HyperEdge:
        node_ids = [subject_node.node_id, fact_node.node_id]
        roles = {subject_node.node_id: "subject", fact_node.node_id: "state_fact"}
        if event_node is not None:
            node_ids.append(event_node.node_id)
            roles[event_node.node_id] = "evidence_event"
        description = f"{subject} {predicate} {object_}"
        edge = self._edge(
            edge_type="state",
            relation="describes_entity_state",
            description=description,
            node_ids=node_ids,
            roles=roles,
            polarity=polarity,
            context=context,
        )
        self.attach_fact_triples_to_edge(fact_node, edge, roles.get(fact_node.node_id))
        return edge

    def build_correction_edge(
        self,
        old_fact: MemoryNode,
        new_fact: MemoryNode,
        context: AssemblyContext,
    ) -> HyperEdge:
        return self._edge(
            edge_type="correction",
            relation="invalidates_previous_fact",
            description=f"{new_fact.content} invalidates {old_fact.content}",
            node_ids=[new_fact.node_id, old_fact.node_id],
            roles={new_fact.node_id: "new_fact", old_fact.node_id: "invalidated_fact"},
            polarity="neutral",
            context=context,
        )

    def attach_fact_triples_to_edge(self, fact_node: MemoryNode, edge: HyperEdge, role: str | None) -> None:
        for triple in fact_node.local_graph.triples:
            triple.scope_edge_id = edge.edge_id
            triple.role_in_edge = role
            triple.edge_relation = edge.relation

    def _edge(
        self,
        *,
        edge_type: str,
        relation: str,
        description: str,
        node_ids: list[str],
        roles: dict[str, str],
        context: AssemblyContext,
        polarity: str = "positive",
    ) -> HyperEdge:
        source_scope = {
            "session_id": context.metadata.get("session_id"),
            "turn": context.current_turn,
            "date": context.metadata.get("date"),
        }
        edge_fingerprint = make_fingerprint(
            description,
            {
                "edge_type": edge_type,
                "relation": relation,
                "roles": sorted(roles.values()),
                "source_scope": source_scope,
            },
        )
        return HyperEdge(
            edge_id=make_edge_id(context.namespace, edge_fingerprint),
            namespace=context.namespace,
            edge_fingerprint=edge_fingerprint,
            edge_type=edge_type,
            relation=relation,
            description=description,
            polarity=polarity,  # type: ignore[arg-type]
            member_policy=self.config.hyperedges.member_policy_default,  # type: ignore[arg-type]
            member_signature=make_member_signature(node_ids, roles),
            node_ids=list(dict.fromkeys(node_ids)),
            roles=roles,
            weights={node_id: 1.0 for node_id in node_ids},
            metadata=source_metadata(context, source_ref=edge_type),
            time=make_time_bundle(
                current_turn=context.current_turn,
                event_time=context.metadata.get("date"),
                valid_start=context.metadata.get("date"),
            ),
        )
