from __future__ import annotations

from datetime import datetime
from typing import Any
from typing_extensions import TypedDict
from pydantic import BaseModel


class FetchResult(BaseModel):
    server: str
    tool_name: str
    success: bool
    data: list[dict] | None = None
    error: str | None = None
    fetched_at: datetime
    source_url: str
    source_name: str


class ColumnProfile(BaseModel):
    name: str
    dtype: str  # temporal | numeric | categorical | text
    sample_values: list[Any]
    null_rate: float
    cardinality: int


class ReconciliationResult(BaseModel):
    success: bool
    data: list[dict] | None = None
    column_profiles: list[ColumnProfile] = []
    warnings: list[str] = []
    provenance_notes: list[str] = []
    error: str | None = None
    row_count_original: int = 0
    row_count_sampled: int = 0


class ChartPlanResult(BaseModel):
    success: bool
    chart_type: str | None = None
    vega_spec: dict | None = None
    strategy: str = "template"  # "template" | "codegen"
    codegen_prompt: str | None = None
    confidence: float = 1.0
    explanation: str = ""
    error: str | None = None


class ChartEvaluation(BaseModel):
    data_fit_score: int
    intent_match_score: int
    issues: list[str] = []
    suggested_fix: str | None = None


class ProvenanceItem(BaseModel):
    source_name: str
    source_url: str
    freshness: datetime
    series_id: str | None = None
    row_count: int | None = None


class TraceEvent(BaseModel):
    step: str
    status: str  # started | completed | failed | skipped
    duration_ms: int | None = None
    message: str | None = None
    metadata: dict = {}


class PipelineState(TypedDict, total=False):
    query: str
    session_id: str
    fetch_results: list[FetchResult]
    reconciled_data: ReconciliationResult | None
    chart_plan: ChartPlanResult | None
    evaluation: ChartEvaluation | None
    iteration: int
    spec_history: list[dict]
    final_spec: dict | None
    provenance: list[ProvenanceItem]
    error: str | None
    pipeline_trace: list[TraceEvent]
    warnings: list[str]
    codegen_used: bool
    chart_response: dict | None  # serialized ChartResponse, set by renderer node
