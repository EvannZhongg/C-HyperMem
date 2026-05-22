from __future__ import annotations

from typing import Any

from c_hypermem.config import MemoryConfig
from c_hypermem.errors import IngestionNotConfiguredError
from c_hypermem.pipeline.extraction import ExtractionContext, MemoryExtractor
from c_hypermem.pipeline.local_graph_builder import LocalGraphBuilder
from c_hypermem.pipeline.maintenance import GraphMaintenance
from c_hypermem.pipeline.view_projection import ViewProjector
from c_hypermem.schema import AgentInteraction, IngestionOutput, MemoryImportBatch, Message


class IngestionPipeline:
    def __init__(
        self,
        config: MemoryConfig,
        *,
        extractor: MemoryExtractor | None = None,
        view_projector: ViewProjector | None = None,
    ) -> None:
        self.config = config
        self.extractor = extractor
        self.local_graph_builder = LocalGraphBuilder()
        self.view_projector = view_projector
        self.maintenance = GraphMaintenance()

    def ingest_interaction(
        self,
        interaction: AgentInteraction,
        *,
        namespace: str,
        current_turn: int,
    ) -> IngestionOutput:
        messages: list[Message] = []
        if interaction.user_input:
            messages.append(interaction.user_input)
        if interaction.assistant_output:
            messages.append(interaction.assistant_output)
        for observation in interaction.observations:
            messages.append(
                Message(
                    role=f"observation:{observation.type}",
                    content=observation.content,
                    timestamp=observation.timestamp,
                    metadata=observation.metadata,
                )
            )
        metadata = dict(interaction.metadata)
        if interaction.tool_calls:
            metadata["tool_calls"] = [call.model_dump(mode="json") for call in interaction.tool_calls]
        if interaction.tool_results:
            metadata["tool_results"] = [result.model_dump(mode="json") for result in interaction.tool_results]
        if interaction.attachments:
            metadata["attachments"] = [attachment.model_dump(mode="json") for attachment in interaction.attachments]
        if interaction.trace:
            metadata["trace"] = interaction.trace
        return self._ingest_messages(messages, namespace=namespace, metadata=metadata, current_turn=current_turn)

    def ingest_batch(
        self,
        batch: MemoryImportBatch,
        *,
        namespace: str,
        current_turn: int,
    ) -> IngestionOutput:
        return self._ingest_messages(
            batch.messages,
            namespace=namespace,
            metadata=batch.metadata,
            current_turn=current_turn,
        )

    def _ingest_messages(
        self,
        messages: list[Message],
        *,
        namespace: str,
        metadata: dict[str, Any],
        current_turn: int,
    ) -> IngestionOutput:
        if not messages:
            return IngestionOutput()
        if self.extractor is None:
            raise IngestionNotConfiguredError(
                "No memory extractor is configured. Pass an explicit extractor to Memory(...)."
            )
        context = ExtractionContext(namespace=namespace, metadata=metadata, current_turn=current_turn)
        extracted = self.extractor.extract(messages, context)
        nodes = extracted.nodes
        edges = extracted.edges
        nodes = self.local_graph_builder.build(nodes)
        if self.view_projector is not None:
            edges.extend(
                self.view_projector.project(
                    nodes,
                    namespace=namespace,
                    metadata=metadata,
                    current_turn=current_turn,
                )
            )
        nodes, edges = self.maintenance.apply(nodes, edges)
        return IngestionOutput(nodes=nodes, edges=edges)
