from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request


def make_channel_router() -> APIRouter:
    """Create the webhook router. Reads channel_manager from app.state at request time."""
    router = APIRouter(prefix="/channels", tags=["channels"])

    @router.post("/{platform}/webhook")
    async def platform_webhook(platform: str, request: Request):
        channel_manager = getattr(request.app.state, "channel_manager", None)
        if channel_manager is None:
            raise HTTPException(status_code=503, detail="Channel manager not initialized")
        adapter = channel_manager.get_adapter(platform)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"Platform '{platform}' not connected")
        payload = await request.json()
        if hasattr(adapter, "handle_webhook"):
            result = await adapter.handle_webhook(payload)
            if result is not None:
                return result
        return {"ok": True}

    return router
