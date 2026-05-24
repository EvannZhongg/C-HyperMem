from __future__ import annotations

from c_hypermem.pipeline.context import AssemblyContext
from c_hypermem.pipeline.entity_resolution import EntityResolution
from c_hypermem.pipeline.graph_utils import dedupe_labels, event_fallback_text, source_metadata, string_list
from c_hypermem.pipeline.local_graph_builder import LocalGraphBuilder
from c_hypermem.schema import (
    ExtractedAssertion,
    ExtractedEntity,
    ExtractedEvent,
    LocalNodeGraph,
    MemoryNode,
)
from c_hypermem.utils.ids import make_fingerprint, make_node_id
from c_hypermem.utils.text import normalize_text, truncate
from c_hypermem.utils.time import make_time_bundle, touch_node_update


class NodeBuilder:
    """Build or update MemoryNodes from extracted candidates."""

    def __init__(self, local_graph_builder: LocalGraphBuilder | None = None) -> None:
        self.local_graph_builder = local_graph_builder or LocalGraphBuilder()

    def build_event_node(self, events: list[ExtractedEvent], context: AssemblyContext) -> MemoryNode | None:
        if events:
            summary = "; ".join(truncate(event.summary, 180) for event in events if event.summary).strip()
            event_time = next((event.time for event in events if event.time), None)
            participants = {
                participant.name: participant.role or "participant"
                for event in events
                for participant in event.participants
                if participant.name
            }
        else:
            summary = truncate(event_fallback_text(context.metadata), 220)
            event_time = context.metadata.get("date") or context.metadata.get("timestamp")
            participants = {}
        if not summary:
            return None

        session_id = context.metadata.get("session_id") or context.metadata.get("conversation_id")
        canonical = summary
        hint = {"session_id": session_id, "turn": context.current_turn} if session_id else {"turn": context.current_turn}
        fingerprint = make_fingerprint(canonical, hint)
        node = MemoryNode(
            node_id=make_node_id(context.namespace, fingerprint),
            namespace=context.namespace,
            canonical_text=canonical,
            normalized_text=normalize_text(canonical),
            fingerprint=fingerprint,
            node_labels=["event"],
            content=canonical,
            summary=summary,
            attributes={"participants": participants} if participants else {},
            metadata=source_metadata(context, source_ref="interaction", extra={"event_count": len(events)}),
            time=make_time_bundle(
                current_turn=context.current_turn,
                event_time=event_time,
                source_timestamp=context.metadata.get("timestamp"),
                valid_start=event_time,
            ),
            local_graph=LocalNodeGraph(),
        )
        return self.local_graph_builder.build_event_node(node, participants)

    def build_or_update_entity_node(
        self,
        entity: ExtractedEntity,
        resolution: EntityResolution,
        context: AssemblyContext,
    ) -> MemoryNode:
        aliases = sorted(resolution.aliases)
        if resolution.node is not None:
            return self.update_entity_node(resolution.node, entity, aliases, context)

        canonical_name = entity.name.strip()
        hint = {"entity_type": entity.entity_type} if entity.entity_type else None
        fingerprint = make_fingerprint(canonical_name, hint)
        node = MemoryNode(
            node_id=make_node_id(context.namespace, fingerprint),
            namespace=context.namespace,
            canonical_text=canonical_name,
            normalized_text=normalize_text(canonical_name),
            fingerprint=fingerprint,
            node_labels=dedupe_labels(["entity", *entity.labels]),
            content=canonical_name,
            summary=canonical_name,
            attributes={
                "canonical_name": canonical_name,
                "display_name": canonical_name,
                "entity_type": entity.entity_type,
                "aliases": aliases,
                **entity.attributes,
            },
            metadata=source_metadata(context, source_ref=entity.source_ref),
            time=make_time_bundle(current_turn=context.current_turn),
            local_graph=LocalNodeGraph(),
        )
        return self.local_graph_builder.build_entity_node(node)

    def update_entity_node(
        self,
        node: MemoryNode,
        entity: ExtractedEntity,
        aliases: list[str],
        context: AssemblyContext,
    ) -> MemoryNode:
        node.node_labels = dedupe_labels([*node.node_labels, "entity", *entity.labels])
        existing_aliases = set(string_list(node.attributes.get("aliases")))
        node.attributes["aliases"] = sorted(existing_aliases.union(aliases))
        if entity.entity_type and not node.attributes.get("entity_type"):
            node.attributes["entity_type"] = entity.entity_type
        node.attributes.update({key: value for key, value in entity.attributes.items() if value not in (None, [], {})})
        node.metadata.update(source_metadata(context, source_ref=entity.source_ref))
        self.local_graph_builder.build_entity_node(node)
        return touch_node_update(node, context.current_turn)

    def build_fact_node(
        self,
        assertion: ExtractedAssertion,
        subject_node: MemoryNode,
        context: AssemblyContext,
    ) -> MemoryNode:
        canonical = assertion_text(assertion)
        fingerprint = make_fingerprint(
            canonical,
            {
                "subject_node_id": subject_node.node_id,
                "predicate": normalize_text(assertion.predicate),
            },
        )
        labels = dedupe_labels(["fact", *assertion.labels])
        if looks_like_preference(assertion):
            labels.append("preference")
        labels = dedupe_labels(labels)
        node = MemoryNode(
            node_id=make_node_id(context.namespace, fingerprint),
            namespace=context.namespace,
            canonical_text=canonical,
            normalized_text=normalize_text(canonical),
            fingerprint=fingerprint,
            node_labels=labels,
            content=canonical,
            summary=canonical,
            attributes={
                "subject": assertion.subject,
                "subject_node_id": subject_node.node_id,
                "predicate": assertion.predicate,
                "object": assertion.object,
                "polarity": assertion.polarity,
                **assertion.attributes,
            },
            metadata=source_metadata(context, source_ref=assertion.source_ref),
            time=make_time_bundle(
                current_turn=context.current_turn,
                event_time=assertion.time or context.metadata.get("date"),
                valid_start=assertion.time or context.metadata.get("date"),
            ),
            local_graph=LocalNodeGraph(),
        )
        return self.local_graph_builder.build_fact_node(node, assertion)


def collect_entities(
    events: list[ExtractedEvent],
    assertions: list[ExtractedAssertion],
    entities: list[ExtractedEntity],
) -> list[ExtractedEntity]:
    by_name: dict[str, ExtractedEntity] = {}
    for entity in entities:
        key = normalize_text(entity.name)
        if not key:
            continue
        by_name.setdefault(key, entity)
    for event in events:
        for participant in event.participants:
            key = normalize_text(participant.name)
            if key and key not in by_name:
                by_name[key] = ExtractedEntity(name=participant.name, labels=["participant"], aliases=[])
    for assertion in assertions:
        key = normalize_text(assertion.subject)
        if key and key not in by_name:
            by_name[key] = ExtractedEntity(name=assertion.subject, labels=["referent"], aliases=[])
    return list(by_name.values())


def assertion_text(assertion: ExtractedAssertion) -> str:
    return " ".join(part for part in [assertion.subject, assertion.predicate, assertion.object] if part).strip()


def looks_like_preference(assertion: ExtractedAssertion) -> bool:
    predicate = normalize_text(assertion.predicate)
    return any(token in predicate for token in ["prefer", "like", "favorite", "favourite"])
