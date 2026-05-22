---
id: extraction.fact
version: 0.1.0
owner: c_hypermem
inputs:
  - event_text
  - metadata
outputs:
  - facts
---

# Task

Extract durable candidate facts from the event text.

# Constraints

- Do not generate node ids, edge ids, entity ids, triple ids, namespaces, or storage keys.
- Prefer concise facts that can be reused across views.
- Include source hints and confidence when available.

