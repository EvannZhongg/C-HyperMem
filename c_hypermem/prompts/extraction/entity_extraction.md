---
id: extraction.entity
version: 0.1.0
owner: c_hypermem
inputs:
  - event_text
  - facts
outputs:
  - entities
---

# Task

Extract candidate entities from the text.

# Output

Return compact JSON with entity names, entity types, and aliases. Do not output system
identifiers, storage keys, scores, importance values, or graph structure.

