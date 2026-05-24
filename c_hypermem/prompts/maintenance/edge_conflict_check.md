---
id: maintenance.edge_conflict_check
version: 0.2.0
owner: c_hypermem
stage: cluster_assignment
---

# Role

You update the health/conflict state of an EdgeCluster after a new edge is
attached to it.

This prompt does not decide whether edges should merge. It only checks whether
the cluster now contains mutually incompatible relationship statements.

# Input

The caller will provide:

- `cluster_description`
- `cluster_labels`
- `existing_cluster_edges`: relationship statements already in the cluster
- `new_edge`: the edge being attached

# Conflict States

- `none`: cluster edges can all be true together.
- `contains_conflict`: at least two statements clearly conflict.
- `needs_review`: possible conflict, missing time scope, or ambiguous wording.

Use time scope carefully. Different states at different times are not conflicts
if the timeline is clear.

# Output JSON

Return exactly one JSON object:

```json
{
  "conflict_state": "none|contains_conflict|needs_review",
  "affected_edge_refs": ["edge:1", "new_edge"],
  "relation_to_cluster": "supports|elaborates|updates|contradicts|duplicate_candidate",
  "rationale": "The new edge updates an older state but does not conflict because time differs."
}
```

# Constraints

Do not output system IDs, storage keys, scores, confidence, or merge decisions.
Use only caller-provided refs.
