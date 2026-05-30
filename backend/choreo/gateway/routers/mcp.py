import time
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, delete
from choreo.db import SessionLocal, McpServerRow
from choreo.models.mcp import McpServer, McpServerCreate, McpServerPatch, ToolConfig

router = APIRouter()


def _row_to_model(row: McpServerRow) -> McpServer:
    tools_raw = row.tools_config or {}
    tools_config = {
        k: ToolConfig(**v) if isinstance(v, dict) else v
        for k, v in tools_raw.items()
    }
    return McpServer(
        name=row.name,
        transport=row.transport,
        command=row.command,
        args=row.args or [],
        url=row.url,
        env=row.env or {},
        tools_config=tools_config,
        enabled=row.enabled,
        created_at=row.created_at,
    )


@router.get("/", response_model=list[McpServer])
async def list_servers():
    async with SessionLocal() as session:
        result = await session.execute(
            select(McpServerRow).order_by(McpServerRow.created_at)
        )
        return [_row_to_model(r) for r in result.scalars()]


@router.post("/", response_model=McpServer)
async def create_server(body: McpServerCreate):
    async with SessionLocal() as session:
        existing = await session.get(McpServerRow, body.name)
        if existing:
            raise HTTPException(409, f"Server '{body.name}' already exists")
        row = McpServerRow(
            name=body.name,
            transport=body.transport,
            command=body.command,
            args=body.args,
            url=body.url,
            env=body.env,
            tools_config={k: v.model_dump() for k, v in body.tools_config.items()},
            enabled=body.enabled,
            created_at=int(time.time()),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _row_to_model(row)


@router.get("/{name}", response_model=McpServer)
async def get_server(name: str):
    async with SessionLocal() as session:
        row = await session.get(McpServerRow, name)
        if not row:
            raise HTTPException(404, "Server not found")
        return _row_to_model(row)


@router.patch("/{name}", response_model=McpServer)
async def patch_server(name: str, body: McpServerPatch):
    async with SessionLocal() as session:
        row = await session.get(McpServerRow, name)
        if not row:
            raise HTTPException(404, "Server not found")
        if body.transport is not None:
            row.transport = body.transport
        if body.command is not None:
            row.command = body.command
        if body.args is not None:
            row.args = body.args
        if body.url is not None:
            row.url = body.url
        if body.env is not None:
            row.env = body.env
        if body.tools_config is not None:
            row.tools_config = {k: v.model_dump() for k, v in body.tools_config.items()}
        if body.enabled is not None:
            row.enabled = body.enabled
        await session.commit()
        await session.refresh(row)
        return _row_to_model(row)


@router.delete("/{name}", status_code=204)
async def delete_server(name: str):
    async with SessionLocal() as session:
        row = await session.get(McpServerRow, name)
        if not row:
            raise HTTPException(404, "Server not found")
        await session.execute(delete(McpServerRow).where(McpServerRow.name == name))
        await session.commit()


@router.post("/reload")
async def reload_mcp():
    """重新加载所有 MCP server 配置和工具，不重启进程。"""
    from choreo.mcp import get_mcp_manager
    try:
        manager = get_mcp_manager()
        await manager.reload()
        return {
            "status": "ok",
            "servers": list(manager.get_all_tools_info().keys()),
        }
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.get("/tools")
async def get_mcp_tools():
    """返回内存中已发现的工具列表（实时状态）。"""
    from choreo.mcp import get_mcp_manager
    try:
        return get_mcp_manager().get_all_tools_info()
    except RuntimeError:
        return {}
