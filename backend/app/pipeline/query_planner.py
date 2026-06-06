from __future__ import annotations

import json
import time

import anthropic
from pydantic import BaseModel

from ..mcp.router import MCPRouter, ToolDefinition
from ..utils.logger import get_logger, log_pipeline_step

logger = get_logger(__name__)


class ToolCall(BaseModel):
    server: str
    tool_name: str
    arguments: dict
    rationale: str


class FetchPlan(BaseModel):
    tool_calls: list[ToolCall]
    can_be_parallel: bool


_PLAN_PROMPT = """\
You are a data-fetching planner for a chart generation system.

User query: {query}

Available tools (JSON array):
{manifest}

Determine which tools to call and with what arguments to satisfy the user's query.
- Prefer specific tools over search tools when you know the series/indicator IDs
- Use parallel fetching when calls are independent
- Country codes for World Bank: use ISO-3 codes (e.g. FRA, DEU, USA)
- FRED common series: GDP (US GDP), GDPC1 (real GDP), CPIAUCSL (CPI), UNRATE (unemployment), SP500 (S&P 500 index), NASDAQCOM (NASDAQ composite), DGS10 (10-year Treasury yield), FEDFUNDS (Fed funds rate), MORTGAGE30US (30-year mortgage rate), DEXUSEU (USD/EUR exchange rate), DCOILWTICO (crude oil price WTI), GVZCLS (gold volatility), BAMLH0A0HYM2 (high yield spread)
- World Bank common indicators (use worldbank.get_indicator with indicator_id + country_codes):
  NY.GDP.MKTP.KD.ZG (GDP growth %), NY.GDP.MKTP.CD (GDP current USD), NY.GDP.PCAP.CD (GDP per capita),
  SP.POP.TOTL (total population), SP.POP.GROW (population growth %), SP.URB.TOTL.IN.ZS (urban population %),
  FP.CPI.TOTL.ZG (CPI inflation %), SL.UEM.TOTL.ZS (unemployment %), SL.UEM.TOTL.NE.ZS (unemployment % national),
  SE.ADT.LITR.ZS (literacy rate), SH.DYN.MORT (child mortality), SP.DYN.LE00.IN (life expectancy),
  EG.USE.PCAP.KG.OE (energy use per capita), EN.ATM.CO2E.PC (CO2 emissions per capita),
  NE.EXP.GNFS.ZS (exports % GDP), BX.KLT.DINV.WD.GD.ZS (FDI % GDP)
- For country-specific World Bank queries, always use worldbank.get_indicator directly — do NOT use search_indicator when you know the indicator
- Only use search tools (search_series, search_indicator, search_ticker) when you genuinely do not know the ID
- Yahoo Finance (yahoo.get_ohlcv): use for any individual stock, ETF, or crypto price history. Common symbols:
  AAPL (Apple), MSFT (Microsoft), GOOGL (Google), AMZN (Amazon), NVDA (NVIDIA), TSLA (Tesla), META (Meta),
  BTC-USD (Bitcoin), ETH-USD (Ethereum), SOL-USD (Solana),
  SPY (S&P 500 ETF), QQQ (NASDAQ ETF), DIA (Dow Jones ETF), IWM (Russell 2000 ETF),
  URTH (MSCI World ETF), ACWI (MSCI All Country World ETF), EEM (MSCI Emerging Markets ETF),
  VGK (FTSE Europe ETF), EWJ (MSCI Japan ETF), FXI (China large-cap ETF),
  GLD (gold ETF), SLV (silver ETF), USO (oil ETF), TLT (20yr Treasury bond ETF)
- For comparison queries ("X vs Y", "compare X and Y"), call yahoo.get_ohlcv ONCE PER SYMBOL — the datasets share the same schema and will be automatically stacked for multi-series charting
- Our World in Data (owid.get_dataset): use for long-run global/country trends. The slug catalog is in the tool description.
  Prefer OWID over World Bank for: CO2/emissions, life expectancy, mortality, internet usage, literacy, HDI, smoking

Return ONLY this JSON, no preamble, no markdown fences:
{{
  "tool_calls": [
    {{
      "server": "<server name>",
      "tool_name": "<server.tool_name>",
      "arguments": {{}},
      "rationale": "<why>"
    }}
  ],
  "can_be_parallel": true
}}"""


async def run_query_planner(
    query: str,
    run_id: str,
    client: anthropic.AsyncAnthropic,
    router: MCPRouter,
) -> FetchPlan:
    t0 = time.monotonic()
    manifest = router.get_manifest()
    manifest_json = json.dumps(
        [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in manifest
        ],
        indent=2,
    )

    try:
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": _PLAN_PROMPT.format(query=query, manifest=manifest_json),
                }
            ],
        )
        raw = resp.content[0].text.strip()
        plan = FetchPlan.model_validate_json(raw)
    except Exception as exc:
        logger.error("Query planner error: %s", exc)
        plan = FetchPlan(tool_calls=[], can_be_parallel=False)

    duration = int((time.monotonic() - t0) * 1000)
    log_pipeline_step(
        run_id,
        query,
        "query_planner",
        duration,
        "success" if plan.tool_calls else "error",
        {"tool_count": len(plan.tool_calls)},
    )
    return plan
