from __future__ import annotations

import json
from typing import Any

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
from c_hypermem.llms.base import LLMClient
from c_hypermem.utils.prompts import PromptRegistry
from c_hypermem.utils.time import touch_node_update, utc_now_iso


class GraphMaintenance:
    """Apply graph maintenance that requires semantic model decisions."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        llm: LLMClient | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.store = store
        self.llm = llm
        self.prompt_registry = prompt_registry or PromptRegistry()

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
        old_facts = self.store.get_nodes(context.namespace, old_fact_ids)
        for old_fact, decision in zip(old_facts, self._check_contradictions(property_key, assertion, old_facts, context)):
            if not decision.should_retire:
                continue
            self._retire_fact(old_fact, new_fact, assertion, context, decision)
            retired_nodes.append(old_fact)
            correction_edges.append(correction_edge_builder(old_fact, new_fact, context))
            retired_properties.append(
                FactPropertyIndexEntry(
                    namespace=context.namespace,
                    property_key=property_key,
                    subject_node_id=old_fact.attributes.get("subject_node_id"),
                    predicate=assertion.predicate,
                    fact_node_id=old_fact.node_id,
                    status=decision.old_status,  # type: ignore[arg-type]
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

    def _check_contradictions(
        self,
        property_key: str,
        assertion: ExtractedAssertion,
        old_facts: list[MemoryNode],
        context: AssemblyContext,
    ) -> list["ContradictionDecision"]:
        if not old_facts:
            return []
        if self.llm is None:
            raise RuntimeError(
                "GraphMaintenance requires an LLM to check overlapping fact contradictions. "
                "Provide a maintenance_llm or configure config.llm."
            )

        prompt = self._render_contradiction_prompt(property_key, assertion, old_facts, context)
        payload = self.llm.generate_json(prompt)
        return _parse_contradiction_payload(payload, old_facts)

    def _render_contradiction_prompt(
        self,
        property_key: str,
        assertion: ExtractedAssertion,
        old_facts: list[MemoryNode],
        context: AssemblyContext,
    ) -> str:
        prompt = self.prompt_registry.load("maintenance.contradiction_check")
        payload = {
            "property_key": property_key,
            "new_assertion": assertion.model_dump(mode="json"),
            "existing_facts": [
                {
                    "ref": f"existing:{index}",
                    "content": fact.content,
                    "status": fact.status,
                    "attributes": fact.attributes,
                    "time": fact.time.model_dump(mode="json"),
                    "metadata": fact.metadata,
                }
                for index, fact in enumerate(old_facts)
            ],
            "temporal_metadata": {
                "current_turn": context.current_turn,
                "date": context.metadata.get("date"),
                "timestamp": context.metadata.get("timestamp"),
            },
        }
        return "\n".join(
            [
                prompt.text,
                "",
                "# Candidate Facts",
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
                "",
                "# Strict JSON Shape",
                (
                    'Return one JSON object with "conflict_state", "affected_existing_refs", '
                    '"recommended_old_status", "valid_time_update", and "rationale".'
                ),
            ]
        )

    def _retire_fact(
        self,
        old_fact: MemoryNode,
        new_fact: MemoryNode,
        assertion: ExtractedAssertion,
        context: AssemblyContext,
        decision: "ContradictionDecision",
    ) -> None:
        old_fact.status = decision.old_status
        old_fact.superseded_by = new_fact.node_id
        old_fact.invalidated_by = new_fact.node_id
        old_fact.status_reason = decision.rationale or "LLM judged the new fact conflicts with this older fact"
        old_fact.status_updated_at = utc_now_iso()
        if old_fact.time.world.valid_time and not old_fact.time.world.valid_time.end:
            old_fact.time.world.valid_time.end = decision.old_end or assertion.time or context.metadata.get("date")
        touch_node_update(old_fact, context.current_turn)


class ContradictionDecision:
    def __init__(
        self,
        *,
        ref: str,
        conflict_state: str,
        old_status: str,
        old_end: str | None = None,
        rationale: str = "",
    ) -> None:
        self.ref = ref
        self.conflict_state = conflict_state
        self.old_status = old_status
        self.old_end = old_end
        self.rationale = rationale

    @property
    def should_retire(self) -> bool:
        return self.conflict_state == "contradiction" and self.old_status in {"retired", "invalidated"}


def _parse_contradiction_payload(payload: dict[str, Any], old_facts: list[MemoryNode]) -> list[ContradictionDecision]:
    conflict_state = str(payload.get("conflict_state") or "uncertain").strip().lower()
    old_status = str(payload.get("recommended_old_status") or "uncertain").strip().lower()
    rationale = str(payload.get("rationale") or "")
    valid_time_update = payload.get("valid_time_update") if isinstance(payload.get("valid_time_update"), dict) else {}
    old_end = valid_time_update.get("old_end")
    affected_refs = payload.get("affected_existing_refs")
    if not isinstance(affected_refs, list):
        affected_refs = []
    affected = {str(ref) for ref in affected_refs}

    decisions: list[ContradictionDecision] = []
    for index, _ in enumerate(old_facts):
        ref = f"existing:{index}"
        if ref in affected:
            decisions.append(
                ContradictionDecision(
                    ref=ref,
                    conflict_state=conflict_state,
                    old_status=_memory_status(old_status),
                    old_end=str(old_end) if old_end else None,
                    rationale=rationale,
                )
            )
        else:
            decisions.append(
                ContradictionDecision(
                    ref=ref,
                    conflict_state="compatible",
                    old_status="active",
                    rationale=rationale,
                )
            )
    return decisions


def _memory_status(value: str) -> str:
    if value in {"active", "retired", "invalidated", "uncertain"}:
        return value
    return "uncertain"
