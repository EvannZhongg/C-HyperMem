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

Extract candidate entities, canonical names, aliases, and entity types.

# Constraints

- Do not generate entity ids.
- Keep canonical names stable and human-readable.
- Preserve aliases separately from canonical names.

