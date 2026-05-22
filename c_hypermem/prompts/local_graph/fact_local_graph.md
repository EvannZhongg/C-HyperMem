---
id: local_graph.fact
version: 0.1.0
owner: c_hypermem
inputs:
  - fact
outputs:
  - triples
---

# Task

Represent one fact as simple subject-predicate-object triples.

# Output

Return compact JSON with subject, predicate, object, time, and source_ref fields. Do not
output system identifiers, scores, importance values, or graph structure.

