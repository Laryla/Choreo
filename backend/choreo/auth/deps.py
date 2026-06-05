from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from choreo.auth.jwt import verify_token
from choreo.config import settings

_bearer = HTTPBearer(auto_error=False)

_LOCAL_USER_ID = "local"


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency: validates Bearer token, returns user_id. Raises 401 on failure."""
    if settings.AUTH_MODE == "all":
        return _LOCAL_USER_ID
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return verify_token(creds.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def require_auth(user_id: str = Depends(get_current_user_id)) -> None:
    """Use as router-level dependency to protect all routes without needing the user_id."""
    pass
