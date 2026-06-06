from __future__ import annotations

import re
import time

import anthropic
from pydantic import BaseModel

from ..utils.logger import get_logger, log_pipeline_step

logger = get_logger(__name__)

_INJECTION_PATTERNS = [
    r"ignore\s+(?:previous|all|prior)\s+instructions",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"act\s+as\s+(?:a\s+)?(?:different|new|another)",
    r"disregard\s+(?:your|all|any)",
    r"<\s*/?(?:system|human|assistant)\s*>",
    r"(?:BEGIN|END)\s+INSTRUCTIONS",
    r"\[INST\]|\[/INST\]",
    r"<\|im_start\|>|<\|im_end\|>",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


class InputGuardResult(BaseModel):
    status: str  # pass | irrelevant | injection | clarification
    message: str | None = None
    question: str | None = None
    clean_query: str | None = None


_GUARD_PROMPT = """\
You are a query classifier for a data visualization application. Analyze the user query and return JSON only.

User query: {query}

Classify the query into exactly one of these categories:
1. "pass" - the query has enough information to fetch and chart data
2. "irrelevant" - not about data or visualization (poetry, general knowledge, coding help, etc.)
3. "clarification_metric" - the metric or indicator to visualize is missing or too vague
4. "clarification_geo" - geographic scope is ambiguous AND cannot be inferred from the metric
5. "clarification_time" - time range is missing

Rules:
- If irrelevant, the query has zero data visualization intent
- Geography is IMPLIED and should NOT be asked for: named stock indices (S&P 500, NASDAQ, Dow Jones, CAC 40, Nikkei, etc.), named commodities (gold, oil, Bitcoin), named countries/regions already in the query, or any metric where geography is inherent
- Only ask for geography when the metric is truly ambiguous across regions (e.g. "show me inflation" with no country)
- Time range "since creation", "historical", "all time", or a specific year/period counts as sufficient
- Prioritize clarification order: metric > geography > time

Return ONLY this JSON, no preamble, no markdown:
{{"category": "<category>", "suggested_question": "<question to ask user if clarification needed, else null>"}}"""


async def run_input_guard(
    query: str,
    run_id: str,
    client: anthropic.AsyncAnthropic,
) -> InputGuardResult:
    t0 = time.monotonic()

    if _INJECTION_RE.search(query):
        log_pipeline_step(run_id, query, "input_guard", 0, "injection")
        return InputGuardResult(
            status="injection",
            message="That query couldn't be processed.",
        )

    try:
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            temperature=0.3,
            messages=[{"role": "user", "content": _GUARD_PROMPT.format(query=query)}],
        )
        raw = resp.content[0].text.strip()
        import json

        parsed = json.loads(raw)
        category = parsed.get("category", "pass")
        question = parsed.get("suggested_question")
    except Exception as exc:
        logger.error("Input guard LLM error: %s", exc)
        category = "pass"
        question = None

    duration = int((time.monotonic() - t0) * 1000)

    if category == "irrelevant":
        log_pipeline_step(run_id, query, "input_guard", duration, "irrelevant")
        return InputGuardResult(
            status="irrelevant",
            message=(
                "I can help you visualize data. Try asking something like "
                "'show me inflation trends for the US since 2010'."
            ),
        )

    if category.startswith("clarification"):
        log_pipeline_step(run_id, query, "input_guard", duration, "clarification")
        return InputGuardResult(
            status="clarification",
            question=question or "Could you clarify your query?",
        )

    log_pipeline_step(run_id, query, "input_guard", duration, "pass")
    return InputGuardResult(status="pass", clean_query=query)
