from __future__ import annotations

from c_hypermem.schema import ExtractedAssertion, LocalTriple, MemoryNode


class LocalGraphBuilder:
    """Build uniform LocalNodeGraph payloads for MemoryNodes."""

    def build(self, nodes: list[MemoryNode]) -> list[MemoryNode]:
        return nodes

    def build_event_node(self, node: MemoryNode, participants: dict[str, str]) -> MemoryNode:
        node.local_graph.triples = [
            LocalTriple(subject=name, predicate="participated_as", object=role)
            for name, role in participants.items()
        ]
        node.local_graph.roles = dict(participants)
        return node

    def build_entity_node(self, node: MemoryNode) -> MemoryNode:
        entity_type = node.attributes.get("entity_type")
        if entity_type:
            node.local_graph.attributes["entity_type"] = entity_type
        return node

    def build_fact_node(self, node: MemoryNode, assertion: ExtractedAssertion) -> MemoryNode:
        node.local_graph.triples = [
            LocalTriple(
                subject=assertion.subject,
                predicate=assertion.predicate,
                object=assertion.object,
                qualifiers={"source_ref": assertion.source_ref} if assertion.source_ref else {},
            )
        ]
        node.local_graph.attributes["polarity"] = assertion.polarity
        return node
