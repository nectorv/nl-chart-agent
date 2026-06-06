from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .router import MCPClient, ToolDefinition, ToolResult
from ..utils.logger import get_logger

logger = get_logger(__name__)

_CSV_PATH = Path(__file__).parent.parent.parent / "data" / "country_metadata.csv"
_SOURCE_NAME = "Country Metadata — curated dataset"


class CsvClient(MCPClient):
    def __init__(self) -> None:
        self._df: pd.DataFrame | None = None

    def _load(self) -> pd.DataFrame:
        if self._df is None:
            self._df = pd.read_csv(_CSV_PATH)
        return self._df

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_country_metadata",
                server="csv",
                description=(
                    "Return country metadata (region, income group, population, capital). "
                    "Pass iso_codes list to filter, or omit for all countries."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "iso_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "3-letter ISO codes to filter; omit for all",
                        }
                    },
                },
            ),
            ToolDefinition(
                name="list_regions",
                server="csv",
                description="Return distinct region names from the country metadata dataset.",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="list_income_groups",
                server="csv",
                description="Return distinct income group values from the country metadata dataset.",
                parameters={"type": "object", "properties": {}},
            ),
        ]

    async def call(self, tool_name: str, args: dict) -> ToolResult:
        freshness = datetime.fromtimestamp(_CSV_PATH.stat().st_mtime, tz=timezone.utc)
        base = ToolResult(
            success=True,
            source_name=_SOURCE_NAME,
            source_url="local",
        )

        df = self._load()

        if tool_name == "get_country_metadata":
            iso_codes = args.get("iso_codes")
            if iso_codes:
                subset = df[df["iso_code"].isin(iso_codes)]
            else:
                subset = df
            base.data = subset.to_dict(orient="records")
            return base

        if tool_name == "list_regions":
            base.data = sorted(df["region"].dropna().unique().tolist())
            return base

        if tool_name == "list_income_groups":
            base.data = sorted(df["income_group"].dropna().unique().tolist())
            return base

        return ToolResult(success=False, error=f"Unknown CSV tool: {tool_name}")

    async def health(self) -> str:
        return "connected" if _CSV_PATH.exists() else "error: CSV file missing"
