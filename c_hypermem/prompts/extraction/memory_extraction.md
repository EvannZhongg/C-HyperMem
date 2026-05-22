---
id: extraction.memory
version: 0.1.0
owner: c_hypermem
inputs:
  - agent_interaction
  - metadata
  - node_types
outputs:
  - entities
  - events
  - facts
  - attributes
  - roles
  - triples
  - sources
---

# Task

Extract concise memory candidates from the interaction.

# Output

Return compact JSON with entities, events, facts, attributes, roles, triples, and
source snippets. Use natural-language fields such as name, type, aliases, summary,
time, subject, predicate, object, role, text, and source_ref.

Do not output system identifiers, storage keys, scores, importance values, or
outer graph structure.

