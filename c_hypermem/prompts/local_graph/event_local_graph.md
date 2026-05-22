---
id: local_graph.event
version: 0.1.0
owner: c_hypermem
inputs:
  - event_text
outputs:
  - triples
  - roles
---

# Task

Extract simple triples and participant roles that describe one event.

# Output

Return compact JSON with subject, predicate, object, role, and source_ref fields. Do not
output system identifiers, scores, importance values, or graph structure.

