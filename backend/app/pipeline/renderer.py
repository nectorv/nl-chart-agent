from __future__ import annotations

import json
import time

import anthropic

from ..models.state import FetchResult, PipelineState, ProvenanceItem, TraceEvent
from ..models.responses import ChartResponse
from ..utils.logger import get_logger, log_pipeline_step

logger = get_logger(__name__)


_CODEGEN_PROMPT = """\
You are a Vega-Lite v5 chart generation expert.

{codegen_prompt}

Return ONLY a complete Vega-Lite v5 JSON spec with the data embedded inline.
The spec must use $schema "https://vega.github.io/schema/vega-lite/v5.json".
Dark background: use background "#0f0f0f", label colors "#f0ede8".
No preamble, no markdown fences — only the JSON object."""


async def run_renderer(
    state: PipelineState,
    client: anthropic.AsyncAnthropic,
) -> ChartResponse:
    t0 = time.monotonic()

    # Codegen escape hatch
    chart_plan = state.get("chart_plan")
    codegen_used = state.get("codegen_used", False)

    spec = state.get("final_spec") or (chart_plan.vega_spec if chart_plan else None)

    if not spec and chart_plan and chart_plan.strategy == "codegen" and chart_plan.codegen_prompt:
        try:
            resp = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": _CODEGEN_PROMPT.format(
                            codegen_prompt=chart_plan.codegen_prompt
                        ),
                    }
                ],
            )
            raw = resp.content[0].text.strip()
            spec = json.loads(raw)
            codegen_used = True
            logger.warning("Codegen spec used for query: %s", state["query"])
        except Exception as exc:
            logger.error("Codegen failed: %s", exc)
            spec = {"error": "Failed to generate chart"}

    if not spec:
        spec = {"error": "No chart spec produced"}

    # Assemble provenance
    provenance: list[ProvenanceItem] = []
    for fetch_result in state.get("fetch_results", []):
        if fetch_result.success and fetch_result.source_name:
            series_id: str | None = None
            if "fred" in fetch_result.server.lower():
                parts = fetch_result.tool_name.split(".")
                if len(parts) > 1:
                    args_hint = fetch_result.tool_name
                    # series_id extracted from source_url
                    url = fetch_result.source_url
                    if "/series/" in url:
                        series_id = url.split("/series/")[-1]
            provenance.append(
                ProvenanceItem(
                    source_name=fetch_result.source_name,
                    source_url=fetch_result.source_url,
                    freshness=fetch_result.fetched_at,
                    series_id=series_id,
                    row_count=len(fetch_result.data) if fetch_result.data else 0,
                )
            )

    warnings = list(state.get("warnings", []))
    reconciled = state.get("reconciled_data")
    if reconciled and reconciled.warnings:
        warnings.extend(reconciled.warnings)

    if codegen_used:
        warnings.append("Chart generated via code generation (no matching template found)")

    duration = int((time.monotonic() - t0) * 1000)
    log_pipeline_step(
        state.get("session_id", ""),
        state["query"],
        "renderer",
        duration,
        "success",
    )

    return ChartResponse(
        vega_spec=spec,
        provenance=provenance,
        warnings=warnings,
        pipeline_trace=state.get("pipeline_trace", []),
        codegen_used=codegen_used,
    )
