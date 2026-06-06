from __future__ import annotations

import os

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router as api_router
from .mcp.csv_client import CsvClient
from .mcp.fred_client import FredClient
from .mcp.owid_client import OWIDClient
from .mcp.router import MCPRouter
from .mcp.worldbank_client import WorldBankClient
from .mcp.yahoo_client import YahooFinanceClient
from .utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="NL-to-Chart Agent", version="0.1.0")

    frontend_url = os.getenv("FRONTEND_URL", "")
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://frontend-production-a3ae.up.railway.app",
        "https://frontend-production-50d4.up.railway.app",
    ]
    if frontend_url:
        allowed_origins.append(frontend_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        app.state.anthropic_client = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

        mcp_router = MCPRouter()
        await mcp_router.connect("fred", FredClient())
        await mcp_router.connect("worldbank", WorldBankClient())
        await mcp_router.connect("csv", CsvClient())
        await mcp_router.connect("yahoo", YahooFinanceClient())
        await mcp_router.connect("owid", OWIDClient())
        app.state.mcp_router = mcp_router
        logger.info("MCP router initialized with %d servers", len(mcp_router.servers))

    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
