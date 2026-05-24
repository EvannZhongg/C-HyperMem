from __future__ import annotations

from dataclasses import dataclass, field

from c_hypermem.pipeline.context import AssemblyContext
from c_hypermem.schema import ExtractedEntity, MemoryNode
from c_hypermem.stores.base import MemoryStore
from c_hypermem.utils.text import normalize_text


@dataclass
class EntityResolution:
    node: MemoryNode | None = None
    aliases: set[str] = field(default_factory=set)


class EntityResolver:
    """Resolve extracted entity aliases to existing shared MemoryNodes."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def resolve(self, entity: ExtractedEntity, context: AssemblyContext) -> EntityResolution:
        aliases = entity_aliases(entity)
        normalized_aliases = [normalize_text(alias) for alias in aliases if normalize_text(alias)]
        existing = self.store.find_entity_alias(context.namespace, normalized_aliases, entity.entity_type)
        if existing is None:
            return EntityResolution(aliases=set(aliases))
        existing_nodes = self.store.get_nodes(context.namespace, [existing.node_id])
        if not existing_nodes:
            return EntityResolution(aliases=set(aliases))
        return EntityResolution(node=existing_nodes[0], aliases=set(aliases))


def entity_aliases(entity: ExtractedEntity) -> list[str]:
    return list(dict.fromkeys([entity.name, *entity.aliases]))
