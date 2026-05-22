from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


NodeType = Literal["turn", "event", "fact", "entity", "state", "preference", "task"]


class MemoryView(str, Enum):
    PROVENANCE = "provenance_view"
    ENTITY_STATE = "entity_state_view"
    TEMPORAL = "temporal_view"
    TOPIC_OR_INTENT = "topic_or_intent_view"
    PREFERENCE_PROFILE = "preference_profile_view"
    TASK_OR_PLAN = "task_or_plan_view"


class ValidTime(BaseModel):
    start: str | None = None
    end: str | None = None
    as_of: str | None = None


class WorldTime(BaseModel):
    event_time: str | None = None
    valid_time: ValidTime | None = None
    source_timestamp: str | None = None


class LifecycleTime(BaseModel):
    created_at: str | None = None
    inserted_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None


class ActivationTime(BaseModel):
    created_turn: int | None = None
    inserted_turn: int | None = None
    updated_turn: int | None = None
    last_access_turn: int | None = None
    access_count: int = 0


class TimeBundle(BaseModel):
    world: WorldTime = Field(default_factory=WorldTime)
    lifecycle: LifecycleTime = Field(default_factory=LifecycleTime)
    activation: ActivationTime = Field(default_factory=ActivationTime)


class LocalTriple(BaseModel):
    id: str | None = None
    subject: str
    predicate: str
    object: str
    qualifiers: dict[str, Any] = Field(default_factory=dict)


class LocalNodeGraph(BaseModel):
    triples: list[LocalTriple] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    roles: dict[str, str] = Field(default_factory=dict)


class SharedNode(BaseModel):
    id: str
    namespace: str
    type: NodeType
    content: str
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    time: TimeBundle = Field(default_factory=TimeBundle)
    local_graph: LocalNodeGraph = Field(default_factory=LocalNodeGraph)
    dedupe_key: str | None = None


class ViewEdge(BaseModel):
    id: str
    namespace: str
    view: str
    relation: str
    node_ids: list[str]
    roles: dict[str, str] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    time: TimeBundle = Field(default_factory=TimeBundle)


class Message(BaseModel):
    role: str
    content: str
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str | None = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str | None = None
    content: str = ""
    status: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    type: str = "observation"
    content: str
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Attachment(BaseModel):
    type: str
    uri: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentInteraction(BaseModel):
    type: Literal["agent_interaction"] = "agent_interaction"
    user_input: Message | None = None
    assistant_output: Message | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryImportBatch(BaseModel):
    type: Literal["memory_import_batch"] = "memory_import_batch"
    messages: list[Message]
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionOutput(BaseModel):
    nodes: list[SharedNode] = Field(default_factory=list)
    edges: list[ViewEdge] = Field(default_factory=list)


class SearchResult(BaseModel):
    id: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)

