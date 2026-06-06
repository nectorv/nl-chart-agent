from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from ..mcp.router import MCPRouter
from ..models.state import FetchResult
from ..pipeline.query_planner import FetchPlan
from ..utils.logger import get_logger, log_pipeline_step

logger = get_logger(__name__)


async def _fetch_one(
    router: MCPRouter,
    tool_name: str,
    arguments: dict,
) -> FetchResult:
    t0 = time.monotonic()
    result = await asyncio.wait_for(
        router.call_tool(tool_name, arguments),
        timeout=10.0,
    )
    return FetchResult(
        server=tool_name.split(".")[0],
        tool_name=tool_name,
        success=result.success,
        data=result.data if result.success else None,
        error=result.error,
        fetched_at=datetime.now(timezone.utc),
        source_url=result.source_url,
        source_name=result.source_name,
    )


async def run_data_fetcher(
    plan: FetchPlan,
    run_id: str,
    query: str,
    router: MCPRouter,
) -> list[FetchResult]:
    t0 = time.monotonic()

    async def safe_fetch(call) -> FetchResult:
        try:
            return await _fetch_one(router, call.tool_name, call.arguments)
        except asyncio.TimeoutError:
            return FetchResult(
                server=call.server,
                tool_name=call.tool_name,
                success=False,
                error="Timeout after 10s",
                fetched_at=datetime.now(timezone.utc),
                source_url="",
                source_name="",
            )
        except Exception as exc:
            return FetchResult(
                server=call.server,
                tool_name=call.tool_name,
                success=False,
                error=str(exc),
                fetched_at=datetime.now(timezone.utc),
                source_url="",
                source_name="",
            )

    if plan.can_be_parallel:
        results = await asyncio.gather(*[safe_fetch(c) for c in plan.tool_calls])
        results = list(results)
    else:
        results = []
        for call in plan.tool_calls:
            results.append(await safe_fetch(call))

    failed = [r for r in results if not r.success]
    succeeded = [r for r in results if r.success]

    if failed:
        for f in failed:
            logger.warning("Fetch failed tool=%s error=%s", f.tool_name, f.error)

    duration = int((time.monotonic() - t0) * 1000)
    log_pipeline_step(
        run_id,
        query,
        "data_fetcher",
        duration,
        "success" if succeeded else "error",
        {"succeeded": len(succeeded), "failed": len(failed)},
    )
    return results
