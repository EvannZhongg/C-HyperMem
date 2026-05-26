---
id: maintenance.local_triple_merge
version: 0.1.0
owner: c_hypermem
stage: local_triple_sp_overlap_batch
---

# Role

You route newly extracted local triples against existing active local triples
from the same MemoryNode. The system calls you with a batch of conflicts only
after deterministic candidate selection finds matching normalized subject and
predicate for each incoming triple.

The system owns all IDs, source tracking, graph writes, timestamps, vector
indexes, and status updates. You only decide how the new triple should be
handled semantically.

# Decisions

- `keep_existing`: the existing triple already covers the new triple, or the new
  triple should be discarded. The system will not save the incoming triple.
- `keep_new`: the new triple should replace affected existing triples. The
  system will retire affected existing triples and save the incoming triple.
- `keep_both`: both values can coexist. The system will save the incoming triple
  without retiring existing triples.
- `merge`: combine the incoming triple and affected existing triples into one
  clearer triple. The system will retire affected existing triples and save the
  merged triple.
- `needs_review`: the relationship is unclear. The system will keep the incoming
  triple as uncertain and leave existing active triples unchanged.

# Rules

- Do not infer information that is absent from the provided triples and node
  context.
- Do not output system IDs, source references, storage keys, graph structures,
  scores, confidence, or chain-of-thought.
- Return exactly one JSON object with a `decisions` array containing one
  decision object per conflict, in the same order as the provided conflict
  array.
- Use only caller-provided refs such as `existing:0`.
- For `keep_existing`, `keep_new`, and `merge`, include the affected existing
  refs.
- For `merge`, provide a complete `merged_triple` object.

# Node Context

{{NODE_CONTEXT}}

# Local Triple Conflicts

{{LOCAL_TRIPLE_CONFLICTS}}

# Output JSON

{{STRICT_JSON_SHAPE}}
