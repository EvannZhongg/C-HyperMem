---
id: extraction.fact
version: 0.1.0
owner: c_hypermem
inputs:
  - event_text
  - metadata
outputs:
  - facts
  - sources
---

# Task

Extract durable facts from the text.

# Output

Return compact JSON with facts and source snippets. Use natural-language fields such as
subject, predicate, object, time, and source_ref. Do not output system identifiers,
storage keys, scores, importance values, or graph structure.

