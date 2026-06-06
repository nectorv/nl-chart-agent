from __future__ import annotations

import time
from typing import AsyncIterator

import anthropic
from langgraph.graph import END, StateGraph

from ..mcp.router import MCPRouter
from ..models.state import PipelineState, TraceEvent
from ..models.responses import ChartResponse
from .chart_planner import run_chart_planner
from .data_fetcher import run_data_fetcher
from .evaluator import run_evaluator, should_retry
from .renderer import run_renderer
from .schema_reconciler import run_schema_reconciler
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _trace(step: str, status: str, duration_ms: int | None = None, message: str | None = None) -> TraceEvent:
    return TraceEvent(step=step, status=status, duration_ms=duration_ms, message=message)


def build_graph(
    client: anthropic.AsyncAnthropic,
    router: MCPRouter,
) -> StateGraph:
    graph = StateGraph(PipelineState)

    async def node_fetch(state: PipelineState) -> dict:
        t0 = time.monotonic()
        from .query_planner import run_query_planner

        trace = list(state.get("pipeline_trace", []))
        trace.append(_trace("query_planner", "started"))

        plan = await run_query_planner(
            state["query"],
            state.get("session_id", ""),
            client,
            router,
        )

        trace[-1] = _trace("query_planner", "completed", int((time.monotonic() - t0) * 1000))
        trace.append(_trace("data_fetcher", "started"))

        t1 = time.monotonic()
        fetch_results = await run_data_fetcher(plan, state.get("session_id", ""), state["query"], router)

        all_failed = all(not r.success for r in fetch_results)
        if all_failed:
            trace[-1] = _trace("data_fetcher", "failed", int((time.monotonic() - t1) * 1000), "All fetches failed")
            return {
                "fetch_results": fetch_results,
                "error": "All data fetches failed. The data source may be unavailable.",
                "pipeline_trace": trace,
            }

        trace[-1] = _trace("data_fetcher", "completed", int((time.monotonic() - t1) * 1000))
        return {"fetch_results": fetch_results, "pipeline_trace": trace}

    async def node_reconcile(state: PipelineState) -> dict:
        t0 = time.monotonic()
        trace = list(state.get("pipeline_trace", []))
        trace.append(_trace("schema_reconciler", "started"))

        reconciled = await run_schema_reconciler(
            state["fetch_results"],
            state.get("session_id", ""),
            state["query"],
            client,
        )

        status = "completed" if reconciled.success else "failed"
        trace[-1] = _trace("schema_reconciler", status, int((time.monotonic() - t0) * 1000))

        update: dict = {"reconciled_data": reconciled, "pipeline_trace": trace}
        if not reconciled.success:
            update["error"] = reconciled.error
        return update

    async def node_plan_chart(state: PipelineState) -> dict:
        t0 = time.monotonic()
        trace = list(state.get("pipeline_trace", []))
        trace.append(_trace("chart_planner", "started"))

        feedback = ""
        evaluation = state.get("evaluation")
        if evaluation and evaluation.suggested_fix:
            feedback = f"Issues: {evaluation.issues}. Suggested fix: {evaluation.suggested_fix}"

        chart_plan = await run_chart_planner(
            state["query"],
            state["reconciled_data"],
            state.get("session_id", ""),
            client,
            feedback=feedback,
        )

        status = "completed" if chart_plan.success else "failed"
        trace[-1] = _trace("chart_planner", status, int((time.monotonic() - t0) * 1000))

        spec = chart_plan.vega_spec or {}
        history = list(state.get("spec_history", []))
        history.append(spec)

        update: dict = {
            "chart_plan": chart_plan,
            "spec_history": history,
            "final_spec": spec,
            "pipeline_trace": trace,
            "iteration": state.get("iteration", 0) + 1,
        }
        if not chart_plan.success:
            update["error"] = chart_plan.error
        return update

    async def node_evaluate(state: PipelineState) -> dict:
        t0 = time.monotonic()
        trace = list(state.get("pipeline_trace", []))
        trace.append(_trace("evaluator", "started"))

        evaluation = await run_evaluator(state, client)

        trace[-1] = _trace(
            "evaluator",
            "completed",
            int((time.monotonic() - t0) * 1000),
            f"data_fit={evaluation.data_fit_score} intent={evaluation.intent_match_score}",
        )
        return {"evaluation": evaluation, "pipeline_trace": trace}

    async def node_render(state: PipelineState) -> dict:
        t0 = time.monotonic()
        trace = list(state.get("pipeline_trace", []))
        trace.append(_trace("renderer", "started"))

        response = await run_renderer(state, client)

        trace[-1] = _trace("renderer", "completed", int((time.monotonic() - t0) * 1000))
        return {
            "pipeline_trace": trace,
            "chart_response": response.model_dump() if response else None,
        }

    def route_after_fetch(state: PipelineState) -> str:
        return "error" if state.get("error") else "reconcile"

    def route_after_reconcile(state: PipelineState) -> str:
        return "error" if state.get("error") else "plan_chart"

    def route_after_plan(state: PipelineState) -> str:
        if state.get("error"):
            return "error"
        plan = state.get("chart_plan")
        if plan and plan.strategy == "codegen":
            return "render"
        return "evaluate"

    def route_after_eval(state: PipelineState) -> str:
        return should_retry(state)

    graph.add_node("fetch", node_fetch)
    graph.add_node("reconcile", node_reconcile)
    graph.add_node("plan_chart", node_plan_chart)
    graph.add_node("evaluate", node_evaluate)
    graph.add_node("render", node_render)
    graph.add_node("error", lambda s: s)

    graph.set_entry_point("fetch")
    graph.add_conditional_edges("fetch", route_after_fetch, {"reconcile": "reconcile", "error": "error"})
    graph.add_conditional_edges("reconcile", route_after_reconcile, {"plan_chart": "plan_chart", "error": "error"})
    graph.add_conditional_edges("plan_chart", route_after_plan, {"evaluate": "evaluate", "render": "render", "error": "error"})
    graph.add_conditional_edges("evaluate", route_after_eval, {"retry": "plan_chart", "accept": "render"})
    graph.add_edge("render", END)
    graph.add_edge("error", END)

    return graph.compile()


async def run_pipeline(
    query: str,
    session_id: str,
    client: anthropic.AsyncAnthropic,
    router: MCPRouter,
) -> tuple[ChartResponse | None, str | None]:
    compiled = build_graph(client, router)

    initial_state: PipelineState = {
        "query": query,
        "session_id": session_id,
        "fetch_results": [],
        "reconciled_data": None,
        "chart_plan": None,
        "evaluation": None,
        "iteration": 0,
        "spec_history": [],
        "final_spec": None,
        "provenance": [],
        "error": None,
        "pipeline_trace": [],
        "warnings": [],
        "codegen_used": False,
        "chart_response": None,
    }

    final_state = await compiled.ainvoke(initial_state)

    error = final_state.get("error")
    response_dict = final_state.get("chart_response")
    response = ChartResponse(**response_dict) if response_dict else None

    return response, error
