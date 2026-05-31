import httpx
from choreo.config import settings

_AUTH_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_SCOPE = "read:user user:email"


def get_auth_url(redirect_uri: str, state: str) -> str:
    params = (
        f"client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={_SCOPE.replace(' ', '%20')}"
        f"&state={state}"
    )
    return f"{_AUTH_URL}?{params}"


async def exchange_code(code: str, redirect_uri: str) -> str:
    """Exchange authorization code for access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(f"GitHub token error: {data}")
        return data["access_token"]


async def get_user_info(access_token: str) -> dict:
    """Returns dict with: id, login, email, name, avatar_url."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
