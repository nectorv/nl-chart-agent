from __future__ import annotations

from pydantic import BaseModel
from .state import ProvenanceItem, TraceEvent


class ChartResponse(BaseModel):
    vega_spec: dict
    provenance: list[ProvenanceItem]
    warnings: list[str] = []
    pipeline_trace: list[TraceEvent] = []
    codegen_used: bool = False


class ClarificationResponse(BaseModel):
    type: str = "clarification"
    question: str
    session_id: str


class ErrorResponse(BaseModel):
    type: str
    message: str
    session_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    mcp_servers: dict[str, str]  # server_name -> "connected" | "error"
