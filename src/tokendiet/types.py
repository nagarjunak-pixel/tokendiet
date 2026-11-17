"""Pydantic v2 data contracts for tokendiet compression, FinOps routing, and live audits."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ModelTier(StrEnum):
    LOCAL_FLASH = "local_flash"
    BALANCED_CODING = "balanced_coding"
    FRONTIER_REASONING = "frontier_reasoning"


class TurnKind(StrEnum):
    READ_FILE = "read_file"
    BASH_OUTPUT = "bash_output"
    PYTHON_CONTEXT = "python_context"


class PruneLineResult(BaseModel):
    line_index: int
    raw_score: int
    mandatory: bool
    token_cost: int
    kept: bool
    text: str


class PrunedOutputReport(BaseModel):
    kernel_backend: str
    budget_tokens: int
    halo_radius: int
    total_lines: int
    kept_lines: int
    omitted_lines: int
    original_tokens: int
    compressed_tokens: int
    savings_pct: float
    total_anchors: int
    kept_anchors: int
    anchor_retention_pct: float
    compressed_text: str
    line_details: list[PruneLineResult] = Field(default_factory=list)


class SkeletonReport(BaseModel):
    original_lines: int
    compressed_lines: int
    original_tokens: int
    compressed_tokens: int
    savings_pct: float
    syntax_valid: bool
    preserved_symbols: list[str]
    elided_symbols: list[str]
    compressed_source: str


class SessionTurnInput(BaseModel):
    turn_id: int
    kind: TurnKind
    label: str
    content: str


class SessionTurnSummary(BaseModel):
    turn_id: int
    kind: TurnKind
    label: str
    original_tokens: int
    compressed_tokens: int
    savings_pct: float
    dedup_blocks_replaced: int
    compressed_content: str


class SessionCompressionReport(BaseModel):
    kernel_backend: str
    turn_count: int
    original_tokens: int
    compressed_tokens: int
    tokens_saved: int
    savings_pct: float
    dedup_blocks_replaced: int
    anchor_retention_pct: float
    estimated_frontier_usd_saved: float
    turn_summaries: list[SessionTurnSummary]


class FinOpsRouteDecision(BaseModel):
    selected_tier: ModelTier
    model_id: str
    unit_cost_per_1m_usd: float
    complexity_score: int
    cascade_escalated: bool
    reason: str
    naive_frontier_cost_usd: float
    routed_compressed_cost_usd: float
    cost_reduction_pct: float
    annualized_50_eng_savings_usd: float


class DietBenchmarkTask(BaseModel):
    task_id: str
    title: str
    mode: str
    raw_prompt_tokens: int
    diet_prompt_tokens: int
    prompt_token_savings_pct: float
    raw_latency_ms: float
    diet_latency_ms: float
    raw_verified: bool
    diet_verified: bool
    raw_answer: str
    diet_answer: str


class RealDietAuditReport(BaseModel):
    model: str
    execution_mode: str
    total_tasks: int
    raw_verified_pct: float
    diet_verified_pct: float
    avg_prompt_token_savings_pct: float
    avg_latency_speedup_pct: float
    total_raw_prompt_tokens: int
    total_diet_prompt_tokens: int
    tasks: list[DietBenchmarkTask]
