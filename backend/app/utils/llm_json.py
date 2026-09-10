from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_json_response(raw: str) -> dict | list:
    """Parse a JSON object/array out of an LLM text response.

    Claude sometimes wraps JSON in markdown code fences (```json ... ```)
    despite being told not to. json.loads chokes on the leading backticks
    with a misleading "Expecting value: line 1 column 1" error, so strip
    fences (and, as a fallback, any other leading/trailing prose) before
    parsing.
    """
    text = raw.strip()

    match = _FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]
        start = min(start_candidates, default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise
