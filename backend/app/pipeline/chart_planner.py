from __future__ import annotations

import json
import time

import anthropic
from pydantic import BaseModel, ValidationError

from ..models.chart_specs import CHART_TYPE_MAP, BaseChartSpec
from ..models.state import ChartPlanResult, ColumnProfile, ReconciliationResult
from ..utils.logger import get_logger, log_pipeline_step

logger = get_logger(__name__)


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = []


_CHART_TYPES_DESC = """
Available chart types:
- "bar": categorical/ordinal x, quantitative y, optional color grouping
- "line": temporal x, quantitative y, optional multi-series via color
- "scatter": quantitative x and y, optional color/size
- "area": temporal x, quantitative y, optional stacked
- "heatmap": two categorical/ordinal axes, quantitative color
- "pie": one categorical field + one quantitative value (use sparingly)
"""

_PLANNER_PROMPT = """\
You are a chart planning expert for a data visualization system.

User query: {query}

Dataset column profiles:
{profiles}

{chart_types}

{feedback}

Select the best chart type and map the data columns to chart fields.
Return confidence 0.0-1.0 for how well any template fits.

Return ONLY this JSON (no preamble, no markdown fences):
{{
  "chart_type": "<one of: bar|line|scatter|area|heatmap|pie>",
  "confidence": 0.9,
  "explanation": "<why this chart type>",
  "spec": {{
    "title": "<descriptive chart title>",
    "x_field": "<column name>",
    "y_field": "<column name>",
    "color_field": "<column name or null>",
    "x_type": "<temporal|quantitative|nominal|ordinal>",
    "y_type": "<quantitative>",
    "point": false,
    "stacked": false,
    "horizontal": false,
    "theta_field": "<for pie only>",
    "size_field": "<for scatter only, or null>"
  }}
}}"""


def validate_spec(spec: BaseChartSpec, data: list[dict]) -> ValidationResult:
    if not data:
        return ValidationResult(valid=False, errors=["No data"])
    columns = set(data[0].keys())
    errors: list[str] = []

    if spec.x_field and spec.x_field not in columns:
        errors.append(f"x_field '{spec.x_field}' not found in data columns {list(columns)}")
    if spec.y_field and spec.y_field not in columns:
        errors.append(f"y_field '{spec.y_field}' not found in data columns {list(columns)}")
    if spec.color_field and spec.color_field not in columns:
        errors.append(f"color_field '{spec.color_field}' not found in data columns {list(columns)}")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


async def run_chart_planner(
    query: str,
    reconciled: ReconciliationResult,
    run_id: str,
    client: anthropic.AsyncAnthropic,
    feedback: str = "",
    attempt: int = 0,
) -> ChartPlanResult:
    t0 = time.monotonic()

    if not reconciled.data:
        return ChartPlanResult(success=False, error="No data to plan chart for")

    profiles_json = json.dumps([p.model_dump() for p in reconciled.column_profiles], indent=2)
    feedback_section = f"\nPrevious attempt feedback:\n{feedback}\n" if feedback else ""

    try:
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": _PLANNER_PROMPT.format(
                        query=query,
                        profiles=profiles_json,
                        chart_types=_CHART_TYPES_DESC,
                        feedback=feedback_section,
                    ),
                }
            ],
        )
        raw = resp.content[0].text.strip()
        parsed = json.loads(raw)
    except Exception as exc:
        logger.error("Chart planner LLM error: %s", exc)
        duration = int((time.monotonic() - t0) * 1000)
        log_pipeline_step(run_id, query, "chart_planner", duration, "error")
        return ChartPlanResult(success=False, error=f"LLM error: {exc}")

    chart_type = parsed.get("chart_type", "line")
    confidence = float(parsed.get("confidence", 1.0))
    explanation = parsed.get("explanation", "")
    spec_dict = parsed.get("spec", {})

    if confidence < 0.6:
        logger.warning("Low chart confidence=%.2f, using codegen escape hatch", confidence)
        data_json = json.dumps(reconciled.data[:200], default=str)
        codegen_prompt = (
            f"User query: {query}\n"
            f"Column profiles: {json.dumps([p.model_dump() for p in reconciled.column_profiles])}\n"
            f"Data (first {min(200, len(reconciled.data))} rows):\n{data_json}\n"
            f"Create a Vega-Lite v5 spec that best answers the query. Embed the full data inline."
        )
        duration = int((time.monotonic() - t0) * 1000)
        log_pipeline_step(run_id, query, "chart_planner", duration, "codegen")
        return ChartPlanResult(
            success=True,
            strategy="codegen",
            codegen_prompt=codegen_prompt,
            confidence=confidence,
            explanation=explanation,
        )

    spec_cls = CHART_TYPE_MAP.get(chart_type, CHART_TYPE_MAP["line"])
    try:
        spec_obj = spec_cls(**{k: v for k, v in spec_dict.items() if v is not None and k in spec_cls.model_fields})
    except ValidationError as exc:
        logger.error("Spec construction error: %s", exc)
        duration = int((time.monotonic() - t0) * 1000)
        log_pipeline_step(run_id, query, "chart_planner", duration, "error")
        return ChartPlanResult(success=False, error=f"Spec validation error: {exc}")

    validation = validate_spec(spec_obj, reconciled.data)
    if not validation.valid:
        if attempt == 0:
            logger.warning("Spec validation failed, retrying with errors: %s", validation.errors)
            return await run_chart_planner(
                query,
                reconciled,
                run_id,
                client,
                feedback=f"Previous spec had these errors: {validation.errors}. Fix them.",
                attempt=1,
            )
        duration = int((time.monotonic() - t0) * 1000)
        log_pipeline_step(run_id, query, "chart_planner", duration, "error")
        return ChartPlanResult(success=False, error=f"Spec invalid after retry: {validation.errors}")

    vega_spec = spec_obj.to_vega_lite(reconciled.data)
    duration = int((time.monotonic() - t0) * 1000)
    log_pipeline_step(run_id, query, "chart_planner", duration, "success", {"chart_type": chart_type})

    return ChartPlanResult(
        success=True,
        chart_type=chart_type,
        vega_spec=vega_spec,
        strategy="template",
        confidence=confidence,
        explanation=explanation,
    )
