from __future__ import annotations

import json
import time

import anthropic

from ..models.state import ChartEvaluation, PipelineState
from ..utils.logger import get_logger, log_eval_iteration, log_pipeline_step

logger = get_logger(__name__)


_JUDGE_PROMPT = """\
You are a chart quality judge for a data visualization system.

User's original query: {query}

Chart spec summary:
- Chart type: {chart_type}
- X axis: {x_field}
- Y axis: {y_field}
- Color/grouping: {color_field}
- Title: {title}
- Data rows: {row_count}

Score on two dimensions from 1-5:
- data_fit: Is this chart type appropriate for the data shape and column types?
- intent_match: Does this chart directly answer what the user asked?

Return ONLY this JSON (no preamble, no markdown):
{{
  "data_fit_score": <1-5>,
  "intent_match_score": <1-5>,
  "issues": ["<issue 1>", "<issue 2>"],
  "suggested_fix": "<one sentence suggestion or null>"
}}"""


def _summarize_spec(spec: dict) -> dict:
    enc = spec.get("encoding", {})
    mark = spec.get("mark", {})
    chart_type = mark if isinstance(mark, str) else mark.get("type", "unknown")
    return {
        "chart_type": chart_type,
        "x_field": enc.get("x", {}).get("field", ""),
        "y_field": enc.get("y", {}).get("field", ""),
        "color_field": enc.get("color", {}).get("field", ""),
        "title": spec.get("title", ""),
        "row_count": len(spec.get("data", {}).get("values", [])),
    }


async def run_evaluator(
    state: PipelineState,
    client: anthropic.AsyncAnthropic,
) -> ChartEvaluation:
    t0 = time.monotonic()
    spec = state.get("final_spec") or (
        state["chart_plan"].vega_spec if state.get("chart_plan") else {}
    )
    if not spec:
        return ChartEvaluation(
            data_fit_score=1,
            intent_match_score=1,
            issues=["No spec to evaluate"],
        )

    summary = _summarize_spec(spec)

    try:
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            temperature=0.3,
            messages=[
                {
                    "role": "user",
                    "content": _JUDGE_PROMPT.format(
                        query=state["query"],
                        **summary,
                    ),
                }
            ],
        )
        raw = resp.content[0].text.strip()
        evaluation = ChartEvaluation.model_validate_json(raw)
    except Exception as exc:
        logger.error("Evaluator LLM error: %s", exc)
        evaluation = ChartEvaluation(
            data_fit_score=4,
            intent_match_score=4,
            issues=[],
        )

    duration = int((time.monotonic() - t0) * 1000)
    log_pipeline_step(
        state.get("session_id", ""),
        state["query"],
        "evaluator",
        duration,
        "success",
        {
            "data_fit": evaluation.data_fit_score,
            "intent_match": evaluation.intent_match_score,
        },
    )
    return evaluation


def should_retry(state: PipelineState) -> str:
    iteration = state.get("iteration", 0)
    if iteration >= 3:
        return "accept"

    history = state.get("spec_history", [])
    if len(history) >= 2 and history[-1] == history[-2]:
        logger.info("Oscillation detected at iteration %d — accepting", iteration)
        return "accept"

    evaluation = state.get("evaluation")
    if evaluation is None:
        return "accept"

    if evaluation.data_fit_score < 4 or evaluation.intent_match_score < 4:
        log_eval_iteration(
            run_id=state.get("session_id", ""),
            query=state["query"],
            iteration=iteration,
            data_fit_score=evaluation.data_fit_score,
            intent_match_score=evaluation.intent_match_score,
            issues=evaluation.issues,
            outcome="retry",
        )
        return "retry"

    log_eval_iteration(
        run_id=state.get("session_id", ""),
        query=state["query"],
        iteration=iteration,
        data_fit_score=evaluation.data_fit_score,
        intent_match_score=evaluation.intent_match_score,
        issues=evaluation.issues,
        outcome="accept",
    )
    return "accept"
