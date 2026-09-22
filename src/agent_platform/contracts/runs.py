"""任务及步骤的公开记录契约。"""
from datetime import datetime, timezone
from typing import Literal
from pydantic import Field, JsonValue
from .base import StrictModel
from .environments import Environment
from .errors import ErrorResponse
from .embedding import EmbeddingSnapshot
from .knowledge import FixedKnowledgeReference, EvidenceRecord

RunStatus = Literal['queued', 'running', 'completed', 'failed', 'cancelled']
TERMINAL = frozenset(('completed', 'failed', 'cancelled'))


class StepRecord(StrictModel):
    run_id: str
    step_id: str
    kind: str = 'node'
    package_binding_id: str | None = None
    attempt: int = Field(default=1, ge=1)
    status: Literal['running', 'completed', 'failed'] = 'running'
    execution_path: list[str] = Field(default_factory=list)
    output: JsonValue = None
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    progress: dict[str, JsonValue] = Field(default_factory=dict)
    error: ErrorResponse | None = None


class Run(StrictModel):
    run_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    service_id: str
    instance_id: str
    version: str
    revision: int = Field(ge=1)
    environment_snapshot: list[Environment] = Field(default_factory=list)
    input: JsonValue
    embedding_snapshot: EmbeddingSnapshot | None = None
    knowledge_bindings: list[FixedKnowledgeReference] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    status: RunStatus = 'queued'
    cancel_requested: bool = False
    cancel_phase: Literal['waiting_transport'] | None = None
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    result: JsonValue = None
    error: ErrorResponse | None = None
    steps: list[StepRecord] = Field(default_factory=list)


class RunSubmit(StrictModel):
    service_id: str
    input: JsonValue
    expected_instance_id: str | None = None


class RunResult(StrictModel):
    run_id: str
    instance_id: str
    result: JsonValue
