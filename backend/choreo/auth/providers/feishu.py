import httpx
from choreo.config import settings

_AUTH_URL = "https://open.feishu.cn/open-apis/authen/v1/authorize"
_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token"
_USER_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


def get_auth_url(redirect_uri: str, state: str) -> str:
    params = (
        f"app_id={settings.FEISHU_APP_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )
    return f"{_AUTH_URL}?{params}"


async def exchange_code(code: str, redirect_uri: str) -> str:
    """Exchange authorization code for access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.FEISHU_APP_ID,
                "client_secret": settings.FEISHU_APP_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"Feishu token error: {data}")
        return data["data"]["access_token"]


async def get_user_info(access_token: str) -> dict:
    """Returns dict with: open_id, name, email, avatar_url."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"Feishu user info error: {data}")
        return data["data"]
