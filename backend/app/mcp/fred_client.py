from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from .router import MCPClient, ToolDefinition, ToolResult
from ..utils.logger import get_logger

logger = get_logger(__name__)

_BASE = "https://api.stlouisfed.org/fred"
_SOURCE_NAME = "FRED — Federal Reserve Economic Data"


def _source_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/series/{series_id}"


class FredClient(MCPClient):
    def __init__(self) -> None:
        self._api_key = os.getenv("FRED_API_KEY", "")
        self._http = httpx.AsyncClient(timeout=10.0)

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_series",
                server="fred",
                description="Search FRED for economic time series matching keywords.",
                parameters={
                    "type": "object",
                    "properties": {
                        "keywords": {"type": "string", "description": "Search keywords"},
                    },
                    "required": ["keywords"],
                },
            ),
            ToolDefinition(
                name="get_series",
                server="fred",
                description="Fetch observations for a FRED series in a date range.",
                parameters={
                    "type": "object",
                    "properties": {
                        "series_id": {"type": "string"},
                        "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    },
                    "required": ["series_id"],
                },
            ),
        ]

    async def call(self, tool_name: str, args: dict) -> ToolResult:
        if tool_name == "search_series":
            return await self._search_series(args["keywords"])
        if tool_name == "get_series":
            return await self._get_series(
                args["series_id"],
                args.get("start_date", ""),
                args.get("end_date", ""),
            )
        return ToolResult(success=False, error=f"Unknown FRED tool: {tool_name}")

    async def _search_series(self, keywords: str) -> ToolResult:
        try:
            resp = await self._http.get(
                f"{_BASE}/series/search",
                params={
                    "search_text": keywords,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "limit": 5,
                },
            )
            resp.raise_for_status()
            series = resp.json().get("seriess", [])
            data = [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "frequency": s.get("frequency_short"),
                    "units": s.get("units"),
                    "seasonal_adjustment": s.get("seasonal_adjustment_short"),
                }
                for s in series
            ]
            return ToolResult(
                success=True,
                data=data,
                source_name=_SOURCE_NAME,
                source_url=f"https://fred.stlouisfed.org/",
            )
        except Exception as exc:
            logger.error("FRED search_series error: %s", exc)
            return ToolResult(success=False, error=str(exc))

    async def _get_series(self, series_id: str, start_date: str, end_date: str) -> ToolResult:
        params: dict = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
        }
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date
        try:
            resp = await self._http.get(f"{_BASE}/series/observations", params=params)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            data = [
                {"date": o["date"], "value": o["value"], "series_id": series_id}
                for o in obs
                if o["value"] != "."
            ]
            return ToolResult(
                success=True,
                data=data,
                source_name=_SOURCE_NAME,
                source_url=_source_url(series_id),
            )
        except Exception as exc:
            logger.error("FRED get_series error series_id=%s error=%s", series_id, exc)
            return ToolResult(success=False, error=str(exc))

    async def health(self) -> str:
        try:
            resp = await self._http.get(
                f"{_BASE}/series",
                params={"series_id": "GDP", "api_key": self._api_key, "file_type": "json"},
            )
            return "connected" if resp.status_code == 200 else f"http_{resp.status_code}"
        except Exception as exc:
            return f"error: {exc}"
