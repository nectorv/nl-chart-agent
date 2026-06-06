from __future__ import annotations

import httpx

from .router import MCPClient, ToolDefinition, ToolResult
from ..utils.logger import get_logger

logger = get_logger(__name__)

_BASE = "https://api.worldbank.org/v2"
_SOURCE_NAME = "World Bank — Open Data"


def _source_url(indicator_id: str) -> str:
    return f"https://data.worldbank.org/indicator/{indicator_id}"


class WorldBankClient(MCPClient):
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=10.0)

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_indicator",
                server="worldbank",
                description="Search World Bank indicators by keywords.",
                parameters={
                    "type": "object",
                    "properties": {
                        "keywords": {"type": "string"},
                    },
                    "required": ["keywords"],
                },
            ),
            ToolDefinition(
                name="get_indicator",
                server="worldbank",
                description="Fetch World Bank indicator data for one or more countries.",
                parameters={
                    "type": "object",
                    "properties": {
                        "indicator_id": {"type": "string", "description": "e.g. NY.GDP.MKTP.KD.ZG"},
                        "country_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "ISO-2 or ISO-3 country codes, or 'WLD' for world",
                        },
                        "start_year": {"type": "integer"},
                        "end_year": {"type": "integer"},
                    },
                    "required": ["indicator_id"],
                },
            ),
        ]

    async def call(self, tool_name: str, args: dict) -> ToolResult:
        if tool_name == "search_indicator":
            return await self._search_indicator(args["keywords"])
        if tool_name == "get_indicator":
            return await self._get_indicator(
                args["indicator_id"],
                args.get("country_codes", ["WLD"]),
                args.get("start_year"),
                args.get("end_year"),
            )
        return ToolResult(success=False, error=f"Unknown WorldBank tool: {tool_name}")

    async def _search_indicator(self, keywords: str) -> ToolResult:
        try:
            resp = await self._http.get(
                f"{_BASE}/indicator",
                params={
                    "format": "json",
                    "per_page": 10,
                    "mrv": 1,
                    "searchTerm": keywords,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            items = body[1] if len(body) > 1 and body[1] else []
            data = [
                {
                    "id": ind["id"],
                    "name": ind["name"],
                    "source": ind.get("sourceNote", "")[:200],
                }
                for ind in items
            ]
            return ToolResult(
                success=True,
                data=data,
                source_name=_SOURCE_NAME,
                source_url="https://data.worldbank.org/",
            )
        except Exception as exc:
            logger.error("WorldBank search_indicator error: %s", exc)
            return ToolResult(success=False, error=str(exc))

    async def _get_indicator(
        self,
        indicator_id: str,
        country_codes: list[str],
        start_year: int | None,
        end_year: int | None,
    ) -> ToolResult:
        country_str = ";".join(country_codes) if country_codes else "WLD"
        params: dict = {"format": "json", "per_page": 1000}
        if start_year:
            from datetime import datetime
            params["date"] = f"{start_year}:{end_year or datetime.now().year}"
        try:
            resp = await self._http.get(
                f"{_BASE}/country/{country_str}/indicator/{indicator_id}",
                params=params,
            )
            resp.raise_for_status()
            body = resp.json()
            if len(body) < 2 or not body[1]:
                return ToolResult(
                    success=False,
                    error=f"No data returned for indicator {indicator_id}",
                )
            rows = [
                {
                    "country": r["country"]["value"],
                    "country_code": r["countryiso3code"] or r["country"]["id"],
                    "year": int(r["date"]),
                    "value": r["value"],
                    "indicator_id": indicator_id,
                }
                for r in body[1]
                if r["value"] is not None
            ]
            return ToolResult(
                success=True,
                data=rows,
                source_name=_SOURCE_NAME,
                source_url=_source_url(indicator_id),
            )
        except Exception as exc:
            logger.error("WorldBank get_indicator error %s: %s", indicator_id, exc)
            return ToolResult(success=False, error=str(exc))

    async def health(self) -> str:
        try:
            resp = await self._http.get(
                f"{_BASE}/country/US/indicator/NY.GDP.MKTP.CD",
                params={"format": "json", "mrv": 1},
            )
            return "connected" if resp.status_code == 200 else f"http_{resp.status_code}"
        except Exception as exc:
            return f"error: {exc}"
