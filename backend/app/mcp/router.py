from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ToolDefinition:
    name: str          # namespaced: server.tool
    server: str
    description: str
    parameters: dict   # JSON Schema of arguments


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    source_url: str = ""
    source_name: str = ""


class MCPClient:
    async def call(self, tool_name: str, args: dict) -> ToolResult:
        raise NotImplementedError

    def list_tools(self) -> list[ToolDefinition]:
        raise NotImplementedError

    async def health(self) -> str:
        raise NotImplementedError


class MCPRouter:
    def __init__(self) -> None:
        self.servers: dict[str, MCPClient] = {}
        self.tool_registry: dict[str, str] = {}

    async def connect(self, name: str, client: MCPClient) -> None:
        self.servers[name] = client
        for tool in client.list_tools():
            namespaced = f"{name}.{tool.name}"
            self.tool_registry[namespaced] = name

    async def call_tool(self, tool_name: str, args: dict) -> ToolResult:
        server_name = self.tool_registry.get(tool_name)
        if not server_name:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
        client = self.servers[server_name]
        bare_name = tool_name.removeprefix(f"{server_name}.")
        try:
            result = await client.call(bare_name, args)
            result.data = self.sanitize(result.data)
            return result
        except Exception as exc:
            logger.error("MCP call failed tool=%s error=%s", tool_name, exc)
            return ToolResult(success=False, error=str(exc))

    def get_manifest(self) -> list[ToolDefinition]:
        tools: list[ToolDefinition] = []
        for name, client in self.servers.items():
            for tool in client.list_tools():
                tools.append(
                    ToolDefinition(
                        name=f"{name}.{tool.name}",
                        server=name,
                        description=tool.description,
                        parameters=tool.parameters,
                    )
                )
        return tools

    def sanitize(self, data: Any) -> Any:
        if isinstance(data, str):
            return f"[TOOL_DATA_START]\n{data}\n[TOOL_DATA_END]"
        return data

    async def health(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for name, client in self.servers.items():
            results[name] = await client.health()
        return results
