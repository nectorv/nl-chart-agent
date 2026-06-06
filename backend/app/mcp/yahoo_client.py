from __future__ import annotations

import asyncio

import yfinance as yf

from .router import MCPClient, ToolDefinition, ToolResult
from ..utils.logger import get_logger

logger = get_logger(__name__)
_SOURCE_NAME = "Yahoo Finance"


class YahooFinanceClient(MCPClient):
    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_ticker",
                server="yahoo",
                description="Search for a stock, ETF, or crypto ticker symbol by company name or keyword.",
                parameters={
                    "type": "object",
                    "properties": {
                        "keywords": {"type": "string", "description": "Company name or search keywords"},
                    },
                    "required": ["keywords"],
                },
            ),
            ToolDefinition(
                name="get_ohlcv",
                server="yahoo",
                description=(
                    "Fetch historical daily price data (open/high/low/close/volume) for a stock, ETF, or crypto. "
                    "Use auto_adjust=True prices. Symbol examples: AAPL, MSFT, GOOGL, TSLA, AMZN, NVDA, "
                    "BTC-USD, ETH-USD, SPY (S&P 500 ETF), QQQ (NASDAQ ETF), GLD (gold ETF)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Ticker symbol"},
                        "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    },
                    "required": ["symbol"],
                },
            ),
        ]

    async def call(self, tool_name: str, args: dict) -> ToolResult:
        if tool_name == "search_ticker":
            return await asyncio.to_thread(self._search_ticker, args["keywords"])
        if tool_name == "get_ohlcv":
            return await asyncio.to_thread(
                self._get_ohlcv,
                args["symbol"],
                args.get("start_date", ""),
                args.get("end_date", ""),
            )
        return ToolResult(success=False, error=f"Unknown Yahoo tool: {tool_name}")

    def _search_ticker(self, keywords: str) -> ToolResult:
        try:
            results = yf.Search(keywords, max_results=5)
            data = [
                {
                    "symbol": q.get("symbol", ""),
                    "name": q.get("shortname") or q.get("longname", ""),
                    "exchange": q.get("exchDisp", q.get("exchange", "")),
                    "type": q.get("quoteType", ""),
                }
                for q in results.quotes
                if q.get("symbol")
            ]
            return ToolResult(
                success=True,
                data=data,
                source_name=_SOURCE_NAME,
                source_url="https://finance.yahoo.com",
            )
        except Exception as exc:
            logger.error("Yahoo search_ticker error: %s", exc)
            return ToolResult(success=False, error=str(exc))

    def _get_ohlcv(self, symbol: str, start_date: str, end_date: str) -> ToolResult:
        try:
            ticker = yf.Ticker(symbol)
            kwargs: dict = {"auto_adjust": True}
            if start_date:
                kwargs["start"] = start_date
            else:
                kwargs["period"] = "max"
            if end_date:
                kwargs["end"] = end_date

            hist = ticker.history(**kwargs)
            if hist.empty:
                return ToolResult(success=False, error=f"No data found for symbol {symbol}")

            hist = hist.reset_index()
            hist.columns = [str(c).lower().replace(" ", "_") for c in hist.columns]

            # Normalize date: strip timezone, format as YYYY-MM-DD
            if "date" in hist.columns:
                hist["date"] = hist["date"].dt.tz_localize(None).dt.strftime("%Y-%m-%d")

            hist["symbol"] = symbol.upper()
            keep = [c for c in ["date", "open", "high", "low", "close", "volume", "symbol"] if c in hist.columns]
            data = hist[keep].to_dict(orient="records")

            return ToolResult(
                success=True,
                data=data,
                source_name=_SOURCE_NAME,
                source_url=f"https://finance.yahoo.com/quote/{symbol.upper()}",
            )
        except Exception as exc:
            logger.error("Yahoo get_ohlcv error symbol=%s error=%s", symbol, exc)
            return ToolResult(success=False, error=str(exc))

    async def health(self) -> str:
        try:
            result = await asyncio.to_thread(self._get_ohlcv, "SPY", "", "")
            return "connected" if result.success else f"error: {result.error}"
        except Exception as exc:
            return f"error: {exc}"
