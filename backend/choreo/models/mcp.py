from typing import Literal
from pydantic import BaseModel


class ToolConfig(BaseModel):
    approval: Literal["auto", "confirm", "deny"] = "confirm"
    enabled: bool = True


class McpServerCreate(BaseModel):
    name: str
    transport: Literal["stdio", "sse", "http"] = "stdio"
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    env: dict[str, str] = {}
    tools_config: dict[str, ToolConfig] = {}
    enabled: bool = True


class McpServerPatch(BaseModel):
    transport: Literal["stdio", "sse", "http"] | None = None
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    tools_config: dict[str, ToolConfig] | None = None
    enabled: bool | None = None


class McpServer(BaseModel):
    name: str
    transport: str
    command: str | None
    args: list[str]
    url: str | None
    env: dict[str, str]
    tools_config: dict[str, ToolConfig]
    enabled: bool
    created_at: int
