import secrets
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from choreo.db import SessionLocal, UserRow
from choreo.auth.jwt import create_access_token, create_refresh_token, verify_token
from choreo.auth.deps import get_current_user_id
from choreo.config import settings
from choreo.auth.providers import github as gh_provider
from choreo.auth.providers import feishu as fs_provider
from jose import JWTError

router = APIRouter()

_PROVIDERS = {
    "github": gh_provider,
    "feishu": fs_provider,
}

# 内存 state 存储（单进程开发用）
_pending_states: dict[str, str] = {}  # state -> provider


def _redirect_uri(provider: str) -> str:
    return f"http://localhost:8000/auth/{provider}/callback"


@router.get("/{provider}/login")
async def login(provider: str):
    if provider not in _PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")
    state = secrets.token_urlsafe(16)
    _pending_states[state] = provider
    url = _PROVIDERS[provider].get_auth_url(_redirect_uri(provider), state)
    return RedirectResponse(url)


@router.get("/{provider}/callback")
async def callback(provider: str, code: str, state: str):
    if _pending_states.pop(state, None) != provider:
        raise HTTPException(400, "Invalid state")

    prov = _PROVIDERS.get(provider)
    if not prov:
        raise HTTPException(404, f"Unknown provider: {provider}")

    try:
        access_token = await prov.exchange_code(code, _redirect_uri(provider))
        info = await prov.get_user_info(access_token)
    except Exception as e:
        raise HTTPException(400, f"OAuth error: {e}")

    # 统一字段提取
    if provider == "github":
        provider_id = str(info["id"])
        name = info.get("name") or info.get("login", "")
        email = info.get("email")
        avatar = info.get("avatar_url")
    else:  # feishu
        provider_id = info.get("open_id", "")
        name = info.get("name", "")
        email = info.get("email")
        avatar = info.get("avatar_url")

    # Upsert 用户
    async with SessionLocal() as session:
        result = await session.execute(
            select(UserRow).where(
                UserRow.provider == provider,
                UserRow.provider_id == provider_id,
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = UserRow(provider=provider, provider_id=provider_id)
            session.add(user)
        user.name = name
        user.email = email
        user.avatar = avatar
        await session.commit()
        await session.refresh(user)

    jwt_access = create_access_token(user.id)
    jwt_refresh = create_refresh_token(user.id)

    frontend_url = (
        f"{settings.FRONTEND_URL}/auth/callback"
        f"?access_token={jwt_access}&refresh_token={jwt_refresh}"
    )
    return RedirectResponse(frontend_url)


@router.post("/refresh")
async def refresh(body: dict):
    """body: {"refresh_token": "..."}  →  {"access_token": "..."}"""
    token = body.get("refresh_token", "")
    try:
        user_id = verify_token(token)
    except JWTError:
        raise HTTPException(401, "Invalid refresh token")
    return {"access_token": create_access_token(user_id)}


@router.get("/me")
async def me(user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as session:
        user = await session.get(UserRow, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return {"id": user.id, "name": user.name, "email": user.email, "avatar": user.avatar}
