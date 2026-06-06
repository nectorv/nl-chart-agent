from __future__ import annotations

import json
import re
import time
from typing import Any

import anthropic
import pandas as pd

from ..models.state import ColumnProfile, FetchResult, ReconciliationResult
from ..utils.logger import get_logger, log_pipeline_step
from ..utils.sampling import sample_dataframe

logger = get_logger(__name__)


# ── Sub-step A: type normalization ──────────────────────────────────────────

_DATE_PATTERNS = [
    r"^\d{4}-\d{2}-\d{2}$",
    r"^\d{4}-\d{2}$",
    r"^\d{4}$",
    r"^\d{4}-Q[1-4]$",
]
_DATE_RE = re.compile("|".join(_DATE_PATTERNS))


def _coerce_column(series: pd.Series) -> tuple[pd.Series, str]:
    sample = series.dropna().astype(str).head(10)

    if sample.str.match(_DATE_RE).all() and len(sample) > 0:
        try:
            converted = pd.to_datetime(series.astype(str), errors="coerce")
            if converted.notna().sum() > 0:
                return converted, "temporal"
        except Exception:
            pass

    cleaned = series.astype(str).str.replace(r"[$,%,€,£]", "", regex=True).str.replace(",", "")
    numeric = pd.to_numeric(cleaned, errors="coerce")
    if numeric.notna().sum() / max(len(series), 1) > 0.7:
        return numeric, "numeric"

    if series.dtype == "object":
        if series.nunique() / max(len(series), 1) < 0.5:
            return series, "categorical"
        return series, "text"

    return series, "text"


def normalize_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    dtypes: dict[str, str] = {}
    for col in df.columns:
        coerced, dtype = _coerce_column(df[col])
        df[col] = coerced
        dtypes[col] = dtype
    return df, dtypes


# ── Sub-step B: schema fingerprinting ───────────────────────────────────────

def fingerprint_dataframe(df: pd.DataFrame, dtypes: dict[str, str]) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []
    for col in df.columns:
        series = df[col]
        sample_vals: list[Any] = []
        try:
            unique_non_null = series.dropna().unique()[:3]
            sample_vals = [str(v) for v in unique_non_null]
        except Exception:
            pass
        null_rate = series.isna().mean()
        try:
            cardinality = series.nunique()
        except Exception:
            cardinality = 0
        profiles.append(
            ColumnProfile(
                name=col,
                dtype=dtypes.get(col, "text"),
                sample_values=sample_vals,
                null_rate=round(float(null_rate), 3),
                cardinality=int(cardinality),
            )
        )
    return profiles


# ── Sub-step C: LLM column alignment ────────────────────────────────────────

from pydantic import BaseModel as _BM


class JoinCandidate(_BM):
    left_col: str
    right_col: str
    confidence: float
    reason: str


class AlignmentPlan(_BM):
    join_candidates: list[JoinCandidate] = []
    rename_map: dict[str, str] = {}
    conflicts: list[str] = []


_ALIGN_PROMPT = """\
You are a data schema alignment expert. Given two dataset fingerprints, identify how to join them.

Left dataset columns:
{left}

Right dataset columns:
{right}

Identify:
1. Join candidates: columns that represent the same concept (e.g. both are country codes, or both are dates)
2. Rename suggestions: columns with same meaning but different names
3. Conflicts: columns that appear similar but have incompatible semantics

Return ONLY this JSON, no preamble, no markdown:
{{
  "join_candidates": [
    {{"left_col": "...", "right_col": "...", "confidence": 0.9, "reason": "..."}}
  ],
  "rename_map": {{}},
  "conflicts": []
}}"""


async def get_alignment_plan(
    left_profiles: list[ColumnProfile],
    right_profiles: list[ColumnProfile],
    client: anthropic.AsyncAnthropic,
) -> AlignmentPlan:
    left_desc = json.dumps([p.model_dump() for p in left_profiles], indent=2)
    right_desc = json.dumps([p.model_dump() for p in right_profiles], indent=2)

    try:
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": _ALIGN_PROMPT.format(left=left_desc, right=right_desc),
                }
            ],
        )
        raw = resp.content[0].text.strip()
        return AlignmentPlan.model_validate_json(raw)
    except Exception as exc:
        logger.error("Alignment plan error: %s", exc)
        return AlignmentPlan()


# ── Main reconciler ──────────────────────────────────────────────────────────

async def run_schema_reconciler(
    fetch_results: list[FetchResult],
    run_id: str,
    query: str,
    client: anthropic.AsyncAnthropic,
) -> ReconciliationResult:
    t0 = time.monotonic()
    warnings: list[str] = []
    provenance_notes: list[str] = []

    valid = [r for r in fetch_results if r.success and r.data]
    if not valid:
        return ReconciliationResult(success=False, error="No valid data from any source")

    # Build dataframes
    dfs: list[tuple[pd.DataFrame, list[ColumnProfile]]] = []
    for r in valid:
        try:
            df = pd.DataFrame(r.data)
            df, dtypes = normalize_dataframe(df)
            profiles = fingerprint_dataframe(df, dtypes)
            dfs.append((df, profiles))
        except Exception as exc:
            warnings.append(f"Failed to parse data from {r.source_name}: {exc}")

    if not dfs:
        return ReconciliationResult(success=False, error="Failed to parse any dataset")

    if len(dfs) == 1:
        df, profiles = dfs[0]
        original_rows = len(df)
        df = sample_dataframe(df, run_id)
        if len(df) < original_rows:
            warnings.append(f"Dataset sampled from {original_rows} to {len(df)} rows for context efficiency")
        data = df.to_dict(orient="records")
        duration = int((time.monotonic() - t0) * 1000)
        log_pipeline_step(run_id, query, "schema_reconciler", duration, "success", {"rows": len(data)})
        return ReconciliationResult(
            success=True,
            data=data,
            column_profiles=profiles,
            warnings=warnings,
            provenance_notes=provenance_notes,
            row_count_original=original_rows,
            row_count_sampled=len(df),
        )

    # Multi-dataset: check if schemas are identical → stack, otherwise join
    left_df, left_profiles = dfs[0]
    right_df, right_profiles = dfs[1]

    left_cols = set(left_df.columns)
    right_cols = set(right_df.columns)
    if left_cols == right_cols:
        stacked = pd.concat([left_df, right_df], ignore_index=True)
        original_rows = len(stacked)
        stacked = sample_dataframe(stacked, run_id)
        if len(stacked) < original_rows:
            warnings.append(f"Stacked dataset sampled from {original_rows} to {len(stacked)} rows")
        stacked_norm, dtypes = normalize_dataframe(stacked)
        profiles = fingerprint_dataframe(stacked_norm, dtypes)
        data = stacked_norm.to_dict(orient="records")
        duration = int((time.monotonic() - t0) * 1000)
        log_pipeline_step(run_id, query, "schema_reconciler", duration, "success", {"rows": len(data), "strategy": "stack"})
        return ReconciliationResult(
            success=True,
            data=data,
            column_profiles=profiles,
            warnings=warnings,
            row_count_original=original_rows,
            row_count_sampled=len(stacked),
        )

    plan = await get_alignment_plan(left_profiles, right_profiles, client)

    best_join = None
    if plan.join_candidates:
        best_join = max(plan.join_candidates, key=lambda c: c.confidence)

    if best_join is None or best_join.confidence < 0.7:
        warnings.append(
            f"Low join confidence ({best_join.confidence if best_join else 0:.2f}) — using left dataset only"
        )
        original_rows = len(left_df)
        left_df = sample_dataframe(left_df, run_id)
        if len(left_df) < original_rows:
            warnings.append(f"Dataset sampled from {original_rows} to {len(left_df)} rows")
        data = left_df.to_dict(orient="records")
        duration = int((time.monotonic() - t0) * 1000)
        log_pipeline_step(run_id, query, "schema_reconciler", duration, "warning", {"rows": len(data)})
        return ReconciliationResult(
            success=True,
            data=data,
            column_profiles=left_profiles,
            warnings=warnings,
            row_count_original=original_rows,
            row_count_sampled=len(left_df),
        )

    # Rename if needed
    if plan.rename_map:
        right_df = right_df.rename(columns=plan.rename_map)

    try:
        merged = pd.merge(
            left_df,
            right_df,
            left_on=best_join.left_col,
            right_on=best_join.right_col,
            how="inner",
        )
    except Exception as exc:
        return ReconciliationResult(success=False, error=f"Join failed: {exc}")

    if len(merged) == 0:
        return ReconciliationResult(
            success=False,
            error="Join produced empty result — key values don't overlap",
        )

    original_rows = len(merged)
    merged = sample_dataframe(merged, run_id)
    if len(merged) < original_rows:
        warnings.append(f"Merged dataset sampled from {original_rows} to {len(merged)} rows")

    merged_norm, dtypes = normalize_dataframe(merged)
    profiles = fingerprint_dataframe(merged_norm, dtypes)
    data = merged_norm.to_dict(orient="records")

    for conflict in plan.conflicts:
        warnings.append(f"Schema conflict: {conflict}")

    duration = int((time.monotonic() - t0) * 1000)
    log_pipeline_step(run_id, query, "schema_reconciler", duration, "success", {"rows": len(data)})

    return ReconciliationResult(
        success=True,
        data=data,
        column_profiles=profiles,
        warnings=warnings,
        provenance_notes=provenance_notes,
        row_count_original=original_rows,
        row_count_sampled=len(merged),
    )
