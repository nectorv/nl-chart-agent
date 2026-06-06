from __future__ import annotations

import io

import httpx
import pandas as pd

from .router import MCPClient, ToolDefinition, ToolResult
from ..utils.logger import get_logger

logger = get_logger(__name__)
_BASE = "https://ourworldindata.org/grapher"
_SOURCE_NAME = "Our World in Data"

CATALOG: dict[str, str] = {
    "co2-emissions-per-capita": "CO2 emissions per capita (tonnes)",
    "annual-co2-emissions-per-country": "Total annual CO2 emissions by country",
    "life-expectancy": "Life expectancy at birth (years)",
    "child-mortality": "Child mortality rate (deaths per 1000 live births)",
    "share-of-individuals-using-the-internet": "Internet users as % of population",
    "share-of-primary-energy-from-renewables": "Renewables as % of primary energy",
    "military-expenditure-share-gdp": "Military expenditure as % of GDP",
    "literacy-rate": "Adult literacy rate (%)",
    "gdp-per-capita-worldbank": "GDP per capita (World Bank, constant 2015 USD)",
    "population": "Total population by country",
    "urbanization-last-500-years": "Urban population share (%)",
    "share-of-adults-who-smoke": "Share of adults who smoke (%)",
    "death-rate-from-air-pollution": "Death rate from air pollution (per 100k)",
    "renewable-energy-consumption": "Renewable energy consumption (TWh)",
    "human-development-index": "Human Development Index (HDI)",
}


class OWIDClient(MCPClient):
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    def list_tools(self) -> list[ToolDefinition]:
        catalog_str = "; ".join(f'"{k}" = {v}' for k, v in CATALOG.items())
        return [
            ToolDefinition(
                name="get_dataset",
                server="owid",
                description=(
                    "Fetch a Our World in Data dataset by slug. "
                    f"Available slugs: {catalog_str}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Dataset slug from the catalog above",
                        },
                        "entities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Country or region names to filter (e.g. ['France', 'Germany', 'World']). "
                                "Leave empty to return all entities."
                            ),
                        },
                        "start_year": {"type": "integer"},
                        "end_year": {"type": "integer"},
                    },
                    "required": ["slug"],
                },
            ),
        ]

    async def call(self, tool_name: str, args: dict) -> ToolResult:
        if tool_name == "get_dataset":
            return await self._get_dataset(
                args["slug"],
                args.get("entities", []),
                args.get("start_year"),
                args.get("end_year"),
            )
        return ToolResult(success=False, error=f"Unknown OWID tool: {tool_name}")

    async def _get_dataset(
        self,
        slug: str,
        entities: list[str],
        start_year: int | None,
        end_year: int | None,
    ) -> ToolResult:
        url = f"{_BASE}/{slug}.csv"
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
        except Exception as exc:
            logger.error("OWID fetch error slug=%s error=%s", slug, exc)
            return ToolResult(success=False, error=str(exc))

        # Normalize column names
        rename: dict[str, str] = {}
        for col in df.columns:
            low = col.lower().strip()
            if low == "entity":
                rename[col] = "entity"
            elif low == "code":
                rename[col] = "code"
            elif low == "year":
                rename[col] = "year"
        df = df.rename(columns=rename)

        # If there's exactly one value column, call it "value"
        value_cols = [c for c in df.columns if c not in ("entity", "code", "year")]
        if len(value_cols) == 1:
            df = df.rename(columns={value_cols[0]: "value"})
            df = df.dropna(subset=["value"])

        # Apply filters
        if entities and "entity" in df.columns:
            df = df[df["entity"].isin(entities)]
        if start_year is not None and "year" in df.columns:
            df = df[df["year"] >= start_year]
        if end_year is not None and "year" in df.columns:
            df = df[df["year"] <= end_year]

        if df.empty:
            return ToolResult(
                success=False,
                error=f"No data for slug='{slug}' with the given filters",
            )

        data = df.to_dict(orient="records")
        return ToolResult(
            success=True,
            data=data,
            source_name=_SOURCE_NAME,
            source_url=f"https://ourworldindata.org/{slug}",
        )

    async def health(self) -> str:
        try:
            resp = await self._http.head(f"{_BASE}/life-expectancy.csv")
            return "connected" if resp.status_code < 400 else f"http_{resp.status_code}"
        except Exception as exc:
            return f"error: {exc}"
