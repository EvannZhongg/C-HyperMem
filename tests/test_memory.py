from __future__ import annotations

import pytest

from c_hypermem import Memory
from c_hypermem.errors import IngestionNotConfiguredError
from c_hypermem.schema import IngestionOutput, LocalNodeGraph, SharedNode, ViewEdge
from c_hypermem.utils.ids import make_edge_id, make_node_id
from c_hypermem.utils.time import make_time_bundle


def test_add_requires_explicit_extractor(tmp_path):
    memory = Memory.from_config({"storage": {"path": str(tmp_path / "memory.sqlite3")}})
    namespace = "test_ns"
    memory.reset(namespace)

    with pytest.raises(IngestionNotConfiguredError):
        memory.add_memory(
            user_input="Alice prefers morning interviews.",
            assistant_output="I will remember that.",
            namespace=namespace,
            metadata={"session_id": "S1", "date": "2024-01-03"},
        )

    assert memory.stats(namespace)["nodes"] == 0
    memory.close()


def test_add_uses_explicit_extractor_only(tmp_path):
    extractor = StaticExtractor()
    memory = Memory.from_config(
        {"storage": {"path": str(tmp_path / "memory.sqlite3")}},
        extractor=extractor,
    )
    namespace = "explicit_ns"
    memory.reset(namespace)

    memory.add(
        [{"role": "user", "content": "raw input is not parsed by C-HyperMem"}],
        namespace=namespace,
        metadata={"session_id": "S1", "date": "2024-01-03"},
    )
    results = memory.search("morning interviews", namespace=namespace, top_k=3)
    stats = memory.stats(namespace)
    memory.close()

    assert extractor.called
    assert stats["nodes"] == 1
    assert stats["edges"] == 1
    assert stats["triples"] == 0
    assert results
    assert "Alice prefers morning interviews" in results[0]["content"]
    assert results[0]["metadata"]["views"] == ["preference_profile_view"]


class StaticExtractor:
    def __init__(self) -> None:
        self.called = False

    def extract(self, messages, context):
        self.called = True
        node = SharedNode(
            id=make_node_id(context.namespace, "preference", "alice-morning-interviews"),
            namespace=context.namespace,
            type="preference",
            content="Alice prefers morning interviews.",
            summary="Alice prefers morning interviews.",
            metadata={
                "source_session_id": context.metadata.get("session_id"),
                "date": context.metadata.get("date"),
            },
            time=make_time_bundle(
                current_turn=context.current_turn,
                event_time=context.metadata.get("date"),
                valid_start=context.metadata.get("date"),
            ),
            local_graph=LocalNodeGraph(),
            dedupe_key="preference:alice-morning-interviews",
        )
        edge = ViewEdge(
            id=make_edge_id(
                context.namespace,
                "preference_profile_view",
                "profile_evidence",
                [node.id],
                {node.id: "preference_evidence"},
            ),
            namespace=context.namespace,
            view="preference_profile_view",
            relation="profile_evidence",
            node_ids=[node.id],
            roles={node.id: "preference_evidence"},
            weights={node.id: 1.0},
            metadata={"created_by": "test_extractor"},
            time=make_time_bundle(current_turn=context.current_turn),
        )
        return IngestionOutput(nodes=[node], edges=[edge])

