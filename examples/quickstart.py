from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c_hypermem import Memory


class DemoExtractor:
    def extract(self, window, context):
        from c_hypermem.schema import MemoryExtraction

        return MemoryExtraction.model_validate(
            {
                "edge_summaries": [
                    {
                        "ref": "e1",
                        "description": "Alice discussed her interview scheduling preference.",
                    }
                ],
                "nodes": [
                    {
                        "ref": "n1",
                        "labels": ["entity", "person"],
                        "canonical_text": "Alice",
                        "summaries": ["Alice is the person whose interview preference was discussed."],
                        "triples": [{"subject": "Alice", "predicate": "is_a", "object": "person"}],
                        "edge_summary_refs": ["e1"],
                    },
                    {
                        "ref": "n2",
                        "labels": ["preference"],
                        "canonical_text": "Alice prefers morning interviews.",
                        "summaries": ["Alice has a scheduling preference for morning interviews."],
                        "triples": [{"subject": "Alice", "predicate": "prefers", "object": "morning interviews"}],
                        "edge_summary_refs": ["e1"],
                    }
                ],
            }
        )


def main() -> None:
    memory = Memory.from_config(
        {
            "storage": {"path": str(Path("runs") / "quickstart.sqlite3")},
        },
        extractor=DemoExtractor(),
    )
    namespace = "quickstart"
    memory.reset(namespace)
    memory.add_memory(
        user_input="Alice prefers morning interviews.",
        assistant_output="I will remember that.",
        namespace=namespace,
        metadata={"session_id": "S1", "date": "2024-01-03"},
    )
    print(memory.search("What does Alice prefer?", namespace=namespace, top_k=3))
    print(memory.stats(namespace))
    memory.close()


if __name__ == "__main__":
    main()
