---
id: extraction.memory
version: 0.3.0
owner: c_hypermem
inputs:
  - agent_interaction
  - metadata
  - node_labels
outputs:
  - nodes
  - edge_summaries
---

# Task

You extract compact long-term memory candidates from an agent interaction.

# Input Processing Rule
You will receive `Context: Recent History` and a `Target to Extract`. 
* Use the Context **only** to resolve pronouns, omitted subjects, or relative time references in the Target. 
* Extract memories **only** if they are explicitly supported by the new information in the Target. Do not extract memories solely from the Context.

# Node Label Guidance

Use these configured node label descriptions as extraction preferences. They are
not a closed whitelist; when a reusable memory object does not fit these labels,
you may emit a precise semantic label in `labels`.

{{NODE_LABELS}}

# Output JSON Schema Rules
Return exactly one JSON object adhering strictly to `{{STRICT_JSON_SHAPE}}`. Never output system IDs, timestamps, outer graph structures, or confidence scores.

* `nodes`: The only carrier for memory objects (entities, events, preferences, tasks, facts). 
* `nodes[].ref`: A temporary local reference (e.g., "n1").
* `nodes[].canonical_text`: A concise standalone statement, understandable without the original message.
* `nodes[].triples`: Describe the node's internal attributes (subject, predicate, object). Leave empty if not applicable.
* `edge_summaries`: Use purely for natural-language descriptions of why a group of nodes should be viewed together. Do not type edges or assign roles.
* `nodes[].edge_summary_refs`: Link the node to the relevant `edge_summaries[].ref`.

# Output JSON

Return exactly one JSON object:

```json
{
  "edge_summaries": [
    {
      "ref": "e1",
      "description": "User stated a morning interview preference in this interaction."
    },
    {
      "ref": "e2",
      "description": "User's interview scheduling preference."
    }
  ],
  "nodes": [
    {
      "ref": "n1",
      "labels": ["entity", "person"],
      "canonical_text": "User",
      "summaries": ["User is the current human user."],
      "triples": [
        {"subject": "User", "predicate": "is_a", "object": "current human user"}
      ],
      "edge_summary_refs": ["e2"]
    },
    {
      "ref": "n2",
      "labels": ["preference"],
      "canonical_text": "User prefers morning interviews.",
      "summaries": ["User has a scheduling preference for morning interviews."],
      "triples": [
        {"subject": "User", "predicate": "prefers", "object": "morning interviews"}
      ],
      "edge_summary_refs": ["e1", "e2"]
    },
    {
      "ref": "n3",
      "labels": ["event"],
      "canonical_text": "User discussed interview scheduling.",
      "summaries": ["User stated an interview scheduling preference."],
      "triples": [
        {"subject": "User", "predicate": "discussed", "object": "interview scheduling"}
      ],
      "edge_summary_refs": ["e1"]
    }
  ],
  "metadata": {}
}
```

## Interaction Metadata

{{INTERACTION_METADATA}}

## Context: Recent History

{{RECENT_CONTEXT}}

## Target to Extract

{{TARGET_MESSAGES}}

# Strict JSON Shape

{{STRICT_JSON_SHAPE}}
