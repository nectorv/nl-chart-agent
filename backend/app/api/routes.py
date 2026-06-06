from __future__ import annotations

import json
import uuid
from typing import AsyncIterator

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..mcp.router import MCPRouter
from ..models.responses import ChartResponse, ErrorResponse, HealthResponse
from ..pipeline.input_guard import run_input_guard
from ..pipeline.orchestrator import run_pipeline
from ..utils.logger import get_logger, new_run_id

logger = get_logger(__name__)
router = APIRouter()

# In-memory clarification session store (keyed by session_id)
_clarification_sessions: dict[str, dict] = {}


class QueryRequest(BaseModel):
    query: str


class ClarifyRequest(BaseModel):
    session_id: str
    answer: str


def _get_client(request: Request) -> anthropic.AsyncAnthropic:
    return request.app.state.anthropic_client


def _get_router(request: Request) -> MCPRouter:
    return request.app.state.mcp_router


async def _stream_pipeline(
    query: str,
    session_id: str,
    client: anthropic.AsyncAnthropic,
    mcp_router: MCPRouter,
) -> AsyncIterator[dict]:
    yield {"event": "trace", "data": json.dumps({"step": "input_guard", "status": "started"})}

    guard_result = await run_input_guard(query, session_id, client)

    if guard_result.status == "injection":
        yield {
            "event": "error",
            "data": json.dumps({"type": "injection", "message": guard_result.message}),
        }
        return

    if guard_result.status == "irrelevant":
        yield {
            "event": "error",
            "data": json.dumps({"type": "irrelevant", "message": guard_result.message}),
        }
        return

    if guard_result.status == "clarification":
        _clarification_sessions[session_id] = {"original_query": query}
        yield {
            "event": "clarification",
            "data": json.dumps(
                {
                    "session_id": session_id,
                    "question": guard_result.question,
                }
            ),
        }
        return

    yield {"event": "trace", "data": json.dumps({"step": "input_guard", "status": "completed"})}
    yield {"event": "trace", "data": json.dumps({"step": "pipeline", "status": "started"})}

    response, error = await run_pipeline(query, session_id, client, mcp_router)

    if error:
        yield {
            "event": "error",
            "data": json.dumps({"type": "pipeline_error", "message": error}),
        }
        return

    if response:
        yield {
            "event": "result",
            "data": response.model_dump_json(),
        }


@router.post("/query")
async def post_query(request: Request, body: QueryRequest):
    session_id = new_run_id()
    client = _get_client(request)
    mcp_router = _get_router(request)

    async def generator():
        async for event in _stream_pipeline(body.query, session_id, client, mcp_router):
            yield event

    return EventSourceResponse(generator())


@router.post("/clarify")
async def post_clarify(request: Request, body: ClarifyRequest):
    session = _clarification_sessions.pop(body.session_id, None)
    if not session:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found or expired"},
        )

    original_query = session["original_query"]
    enriched_query = f"{original_query} {body.answer}"
    client = _get_client(request)
    mcp_router = _get_router(request)

    async def generator():
        async for event in _stream_pipeline(enriched_query, body.session_id, client, mcp_router):
            yield event

    return EventSourceResponse(generator())


@router.get("/health")
async def get_health(request: Request) -> HealthResponse:
    mcp_router = _get_router(request)
    server_status = await mcp_router.health()
    all_ok = all(v == "connected" for v in server_status.values())
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        mcp_servers=server_status,
    )
