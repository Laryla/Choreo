# OAuth2 登录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Choreo 加入 GitHub + 飞书 OAuth2 第三方登录，JWT 会话，所有路由守卫，用户数据隔离。

**Architecture:** 后端用 `authlib` 做 OAuth2 code flow，签发 access token（1h）+ refresh token（30d），frontend 存 localStorage，所有 API 请求携带 access token，401 时自动用 refresh token 续期。数据隔离通过在 `ThreadRow`/`TaskRow` 加 `user_id` 列实现。

**Tech Stack:** Python: `authlib>=1.3`, `python-jose[cryptography]>=3.3`；Frontend: 原生 fetch（无新库）；DB: PostgreSQL via SQLAlchemy。

---

## 文件清单

### 后端新建
| 路径 | 职责 |
|------|------|
| `backend/choreo/auth/__init__.py` | 包入口 |
| `backend/choreo/auth/jwt.py` | create_access_token / create_refresh_token / verify_token |
| `backend/choreo/auth/deps.py` | FastAPI 依赖：get_current_user_id（JWT 验证）|
| `backend/choreo/auth/providers/github.py` | GitHub OAuth：get_auth_url / exchange_code / get_user_info |
| `backend/choreo/auth/providers/feishu.py` | 飞书 OAuth：get_auth_url / exchange_code / get_user_info |
| `backend/choreo/gateway/routers/auth.py` | /auth/{provider}/login + /callback + /refresh + /me |
| `backend/tests/test_auth_jwt.py` | JWT 单元测试 |

### 后端修改
| 路径 | 改动 |
|------|------|
| `backend/pyproject.toml` | 加 authlib, python-jose |
| `backend/choreo/config.py` | 加 GITHUB_CLIENT_ID/SECRET, FEISHU_APP_ID/SECRET, JWT_SECRET, JWT_ALGORITHM, FRONTEND_URL |
| `backend/choreo/db.py` | 新增 UserRow；ThreadRow/TaskRow 加 user_id nullable 列 |
| `backend/choreo/gateway/app.py` | 注册 auth router，给其余 router 加 require_auth 依赖 |
| `backend/choreo/gateway/routers/threads.py` | list/create/get 操作按 user_id 过滤 |
| `backend/choreo/gateway/routers/tasks.py` | list/create/get 操作按 user_id 过滤 |
| `backend/choreo/store/thread_store.py` | list_by_user / create_with_user |

### 前端新建
| 路径 | 职责 |
|------|------|
| `frontend/src/store/authStore.ts` | token 读写 / isAuthenticated / clearTokens |
| `frontend/src/lib/api.ts` | fetch wrapper with auto-refresh on 401 |
| `frontend/src/pages/LoginPage.tsx` | GitHub / 飞书 登录按钮 |
| `frontend/src/pages/AuthCallbackPage.tsx` | 接收 ?access_token=&refresh_token=，存储，跳转 /chat |
| `frontend/src/components/ProtectedRoute.tsx` | 未登录跳 /login |

### 前端修改
| 路径 | 改动 |
|------|------|
| `frontend/src/lib/client.ts` | LangGraph SDK client 带 auth header |
| `frontend/src/App.tsx` | 加 /login + /auth/callback 路由，其余包 ProtectedRoute |
| `frontend/src/components/Topbar/Topbar.tsx` | 右上角用户头像 + 退出登录 |

---

## Task 1: 安装依赖 + 配置

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/choreo/config.py`

- [ ] **Step 1: 在 pyproject.toml 的 dependencies 里加两行**

```toml
"authlib>=1.3",
"python-jose[cryptography]>=3.3",
```

- [ ] **Step 2: 安装**

```bash
cd backend && uv sync
```

期望：无报错。

- [ ] **Step 3: 更新 config.py**

```python
# 在 Settings 类末尾加：

# Auth
JWT_SECRET: str = "change-me-in-production"
JWT_ALGORITHM: str = "HS256"
FRONTEND_URL: str = "http://localhost:5173"

# GitHub OAuth
GITHUB_CLIENT_ID: str = ""
GITHUB_CLIENT_SECRET: str = ""

# 飞书 OAuth
FEISHU_APP_ID: str = ""
FEISHU_APP_SECRET: str = ""
```

- [ ] **Step 4: 在 .env 里填入真实值（本地开发用）**

```bash
# 在 backend/.env 追加
JWT_SECRET=local-dev-secret-change-in-prod
FRONTEND_URL=http://localhost:5173

GITHUB_CLIENT_ID=你的 GitHub OAuth App Client ID
GITHUB_CLIENT_SECRET=你的 GitHub OAuth App Client Secret

FEISHU_APP_ID=你的飞书 App ID
FEISHU_APP_SECRET=你的飞书 App Secret
```

GitHub OAuth App 回调 URL 设为：`http://localhost:8000/auth/github/callback`
飞书 App 重定向 URL 设为：`http://localhost:8000/auth/feishu/callback`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/choreo/config.py
git commit -m "feat(auth): add authlib, python-jose deps and OAuth config"
```

---

## Task 2: 数据库 — UserRow + user_id 列

**Files:**
- Modify: `backend/choreo/db.py`

- [ ] **Step 1: 在 db.py 加 UserRow 和修改现有表**

在 `McpServerRow` 定义后追加：

```python
import uuid as _uuid


class UserRow(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    provider = Column(String, nullable=False)       # "github" | "feishu"
    provider_id = Column(String, nullable=False)    # provider 内部 uid
    email = Column(String, nullable=True)
    name = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    created_at = Column(Integer, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_user_provider"),
    )
```

在 `ThreadRow` 里加一列（在 `created_at` 之前）：
```python
user_id = Column(String, nullable=True, index=True)
```

在 `TaskRow` 里加一列（在 `status` 之前）：
```python
user_id = Column(String, nullable=True, index=True)
```

- [ ] **Step 2: 验证 db.py 可导入并且 init_db 会建表**

```bash
cd backend && uv run python -c "from choreo.db import UserRow, ThreadRow, TaskRow; print('OK')"
```

期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/db.py
git commit -m "feat(auth): add UserRow, user_id to ThreadRow and TaskRow"
```

---

## Task 3: JWT 工具

**Files:**
- Create: `backend/choreo/auth/__init__.py`
- Create: `backend/choreo/auth/jwt.py`
- Create: `backend/tests/test_auth_jwt.py`

- [ ] **Step 1: 建包入口**

```python
# backend/choreo/auth/__init__.py
```

- [ ] **Step 2: 写失败测试**

```python
# backend/tests/test_auth_jwt.py
import pytest
from choreo.auth.jwt import create_access_token, create_refresh_token, verify_token


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    assert verify_token(token) == "user-123"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-456")
    assert verify_token(token) == "user-456"


def test_invalid_token_raises():
    with pytest.raises(Exception):
        verify_token("not.a.real.token")


def test_tampered_token_raises():
    token = create_access_token("user-789")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(Exception):
        verify_token(tampered)
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_auth_jwt.py -v
```

期望：FAIL with `ModuleNotFoundError: No module named 'choreo.auth.jwt'`

- [ ] **Step 4: 实现 jwt.py**

```python
# backend/choreo/auth/jwt.py
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from choreo.config import settings

_ACCESS_EXPIRE = timedelta(hours=1)
_REFRESH_EXPIRE = timedelta(days=30)


def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + _ACCESS_EXPIRE,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + _REFRESH_EXPIRE,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> str:
    """Verify JWT and return user_id. Raises JWTError on failure."""
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise JWTError("Token missing sub claim")
    return user_id
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_auth_jwt.py -v
```

期望：4 个 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/auth/ backend/tests/test_auth_jwt.py
git commit -m "feat(auth): add JWT create/verify utilities"
```

---

## Task 4: FastAPI 认证依赖

**Files:**
- Create: `backend/choreo/auth/deps.py`

- [ ] **Step 1: 新建 deps.py**

```python
# backend/choreo/auth/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from choreo.auth.jwt import verify_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency: validates Bearer token, returns user_id. Raises 401 on failure."""
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return verify_token(creds.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def require_auth(user_id: str = Depends(get_current_user_id)) -> None:
    """Use as router-level dependency to protect all routes without needing the user_id."""
    pass
```

- [ ] **Step 2: 验证可导入**

```bash
cd backend && uv run python -c "from choreo.auth.deps import get_current_user_id, require_auth; print('OK')"
```

期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/auth/deps.py
git commit -m "feat(auth): add FastAPI auth dependencies"
```

---

## Task 5: GitHub OAuth Provider

**Files:**
- Create: `backend/choreo/auth/providers/__init__.py`
- Create: `backend/choreo/auth/providers/github.py`

- [ ] **Step 1: 建包**

```python
# backend/choreo/auth/providers/__init__.py
```

- [ ] **Step 2: 实现 github.py**

```python
# backend/choreo/auth/providers/github.py
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
```

- [ ] **Step 3: 验证可导入**

```bash
cd backend && uv run python -c "from choreo.auth.providers.github import get_auth_url; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/choreo/auth/providers/
git commit -m "feat(auth): add GitHub OAuth provider"
```

---

## Task 6: 飞书 OAuth Provider

**Files:**
- Create: `backend/choreo/auth/providers/feishu.py`

- [ ] **Step 1: 实现 feishu.py**

```python
# backend/choreo/auth/providers/feishu.py
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
```

- [ ] **Step 2: 验证可导入**

```bash
cd backend && uv run python -c "from choreo.auth.providers.feishu import get_auth_url; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/auth/providers/feishu.py
git commit -m "feat(auth): add Feishu OAuth provider"
```

---

## Task 7: Auth 路由

**Files:**
- Create: `backend/choreo/gateway/routers/auth.py`

- [ ] **Step 1: 新建 auth.py**

```python
# backend/choreo/gateway/routers/auth.py
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

# 内存 state 存储（生产可用 Redis；本地 single-process 足够）
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

    # 把 token 传给前端（query param，前端 /auth/callback 页面存 localStorage）
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
```

- [ ] **Step 2: 注册到 app.py**

在 app.py imports 末尾加：
```python
from choreo.gateway.routers import auth as auth_router
from choreo.auth.deps import require_auth
```

在 `app.include_router(threads.router, ...)` 之前加：
```python
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
```

给所有现有 router 加 `dependencies=[Depends(require_auth)]`：
```python
app.include_router(threads.router, prefix="/threads",     tags=["threads"],  dependencies=[Depends(require_auth)])
app.include_router(runs.router,    prefix="/threads",     tags=["runs"],     dependencies=[Depends(require_auth)])
app.include_router(tasks.router,   prefix="/api/tasks",   tags=["tasks"],    dependencies=[Depends(require_auth)])
app.include_router(history.router, prefix="/api/history", tags=["history"],  dependencies=[Depends(require_auth)])
app.include_router(models.router,  prefix="/models",      tags=["models"],   dependencies=[Depends(require_auth)])
app.include_router(skills_router.router, prefix="/api/skills", tags=["skills"], dependencies=[Depends(require_auth)])
app.include_router(mcp_router.router,    prefix="/api/mcp",    tags=["mcp"],    dependencies=[Depends(require_auth)])
```

- [ ] **Step 3: 验证启动无报错**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload &
sleep 3
curl -s http://localhost:8000/auth/github/login -v 2>&1 | grep "location:"
kill %1
```

期望：返回 302 跳转到 GitHub 授权页。

- [ ] **Step 4: 验证 API 现在需要认证**

```bash
curl -s http://localhost:8000/api/threads/ | python3 -m json.tool
```

期望：`{"detail": "Not authenticated"}`

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/gateway/routers/auth.py backend/choreo/gateway/app.py
git commit -m "feat(auth): add auth router, protect all API routes"
```

---

## Task 8: 数据隔离 — Threads + Tasks 按 user_id 过滤

**Files:**
- Modify: `backend/choreo/store/thread_store.py`
- Modify: `backend/choreo/gateway/routers/threads.py`
- Modify: `backend/choreo/gateway/routers/tasks.py`

- [ ] **Step 1: 读 thread_store.py 了解现有接口**

```bash
cat backend/choreo/store/thread_store.py
```

- [ ] **Step 2: 在 thread_store.py 加按 user_id 过滤的方法**

在现有 `list_all` 方法旁边加：

```python
async def list_by_user(self, user_id: str) -> list[Thread]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(ThreadRow)
            .where(ThreadRow.user_id == user_id)
            .order_by(ThreadRow.created_at.desc())
        )
        return [self._row_to_thread(r) for r in result.scalars()]

async def create_for_user(self, thread_id: str, user_id: str) -> None:
    """在 ThreadRow 里记录 thread_id 和 user_id 的归属。"""
    async with SessionLocal() as session:
        existing = await session.get(ThreadRow, thread_id)
        if existing:
            existing.user_id = user_id
        else:
            session.add(ThreadRow(thread_id=thread_id, user_id=user_id))
        await session.commit()
```

- [ ] **Step 3: 修改 threads.py 路由**

在 `list_threads` 中加 user_id 依赖并过滤：

```python
from choreo.auth.deps import get_current_user_id

@router.get("/", response_model=list[Thread])
async def list_threads(user_id: str = Depends(get_current_user_id)):
    return await thread_store.list_by_user(user_id)

@router.post("/", response_model=Thread, status_code=201)
async def create_thread(user_id: str = Depends(get_current_user_id)):
    thread = Thread()
    await thread_store.create_for_user(thread.thread_id, user_id)
    return thread
```

对 `get_thread_state`、`update_thread_state`、`get_thread_messages` 加验证——这里简单通过 SQL 查询 thread 是否属于当前用户：

```python
async def _assert_owns(thread_id: str, user_id: str):
    async with SessionLocal() as session:
        row = await session.get(ThreadRow, thread_id)
    if not row or row.user_id != user_id:
        raise HTTPException(403, "Thread not found")
```

在这三个路由里加 `await _assert_owns(tid, user_id)`。

- [ ] **Step 4: 修改 tasks.py 路由**

类似地，给 `list_tasks` 和 `create_task` 加 `user_id` 依赖，SQL 查询加 `.where(TaskRow.user_id == user_id)` 过滤，`create_task` 时设置 `row.user_id = user_id`。

- [ ] **Step 5: 验证**

```bash
cd backend && uv run python -c "from choreo.store.thread_store import thread_store; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/store/thread_store.py backend/choreo/gateway/routers/threads.py backend/choreo/gateway/routers/tasks.py
git commit -m "feat(auth): isolate threads and tasks by user_id"
```

---

## Task 9: 前端 authStore + API 工具

**Files:**
- Create: `frontend/src/store/authStore.ts`
- Create: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/client.ts`

- [ ] **Step 1: 新建 authStore.ts**

```typescript
// frontend/src/store/authStore.ts
const ACCESS_KEY = "choreo_access_token";
const REFRESH_KEY = "choreo_refresh_token";

export const authStore = {
  getAccessToken: () => localStorage.getItem(ACCESS_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_KEY),
  setTokens: (access: string, refresh: string) => {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clearTokens: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  isAuthenticated: () => !!localStorage.getItem(ACCESS_KEY),
};
```

- [ ] **Step 2: 新建 api.ts — fetch wrapper with auto-refresh**

```typescript
// frontend/src/lib/api.ts
import { authStore } from "@/store/authStore";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = authStore.getRefreshToken();
  if (!refreshToken) return null;
  try {
    const res = await fetch(`${API}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    const { access_token } = await res.json();
    authStore.setTokens(access_token, refreshToken);
    return access_token;
  } catch {
    return null;
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = authStore.getAccessToken();
  const headers = {
    ...init.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  let res = await fetch(`${API}${path}`, { ...init, headers });

  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      res = await fetch(`${API}${path}`, {
        ...init,
        headers: { ...headers, Authorization: `Bearer ${newToken}` },
      });
    } else {
      authStore.clearTokens();
      window.location.href = "/login";
    }
  }

  return res;
}
```

- [ ] **Step 3: 更新 client.ts 让 LangGraph SDK 带 token**

```typescript
// frontend/src/lib/client.ts
import { Client } from "@langchain/langgraph-sdk";
import { authStore } from "@/store/authStore";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

export const getClient = () => {
  const token = authStore.getAccessToken();
  return new Client({
    apiUrl: API,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
};

// 向下兼容：保留 client 导出（用 getClient() 的结果）
export const client = new Proxy({} as ReturnType<typeof getClient>, {
  get(_, prop) {
    return (getClient() as any)[prop];
  },
});
```

- [ ] **Step 4: TypeScript 检查**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

期望：无报错（或仅关于 Proxy 类型的 warning）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/authStore.ts frontend/src/lib/api.ts frontend/src/lib/client.ts
git commit -m "feat(auth): add authStore, apiFetch with token refresh, auth-aware SDK client"
```

---

## Task 10: 前端 Login 页面

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1: 新建 LoginPage.tsx**

```tsx
// frontend/src/pages/LoginPage.tsx
const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center">
      <div className="w-[360px] bg-[#111] rounded-2xl border border-[#222] p-8 flex flex-col items-center gap-6">
        <div className="text-center mb-2">
          <h1 className="text-[20px] font-semibold text-[#e8e8e8]">欢迎使用 Choreo</h1>
          <p className="text-[13px] text-[#666] mt-1">选择登录方式继续</p>
        </div>

        <a
          href={`${API}/auth/github/login`}
          className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl bg-[#1a1a1a] border border-[#2a2a2a] text-[13px] text-[#e8e8e8] hover:border-[#444] transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
          </svg>
          使用 GitHub 登录
        </a>

        <a
          href={`${API}/auth/feishu/login`}
          className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl bg-[#1a1a1a] border border-[#2a2a2a] text-[13px] text-[#e8e8e8] hover:border-[#444] transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none">
            <rect width="24" height="24" rx="6" fill="#3370FF"/>
            <path d="M7 8l5 3 5-3M7 12l5 3 5-3" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          使用飞书登录
        </a>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat(auth): add LoginPage with GitHub and Feishu buttons"
```

---

## Task 11: 前端 AuthCallback 页面

**Files:**
- Create: `frontend/src/pages/AuthCallbackPage.tsx`

- [ ] **Step 1: 新建 AuthCallbackPage.tsx**

```tsx
// frontend/src/pages/AuthCallbackPage.tsx
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { authStore } from "@/store/authStore";

export default function AuthCallbackPage() {
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");

    if (access && refresh) {
      authStore.setTokens(access, refresh);
      navigate("/chat", { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  }, []);

  return (
    <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center">
      <p className="text-[#666] text-[13px]">登录中…</p>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/AuthCallbackPage.tsx
git commit -m "feat(auth): add AuthCallbackPage to store tokens and redirect"
```

---

## Task 12: ProtectedRoute + 路由更新

**Files:**
- Create: `frontend/src/components/ProtectedRoute.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 新建 ProtectedRoute.tsx**

```tsx
// frontend/src/components/ProtectedRoute.tsx
import { Navigate } from "react-router-dom";
import { authStore } from "@/store/authStore";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!authStore.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
```

- [ ] **Step 2: 更新 App.tsx**

读现有 App.tsx，加入：
- `/login` → `<LoginPage />`
- `/auth/callback` → `<AuthCallbackPage />`
- 其余所有路由包 `<ProtectedRoute>`

```tsx
import LoginPage from "@/pages/LoginPage";
import AuthCallbackPage from "@/pages/AuthCallbackPage";
import { ProtectedRoute } from "@/components/ProtectedRoute";

// 路由配置中：
<Route path="/login" element={<LoginPage />} />
<Route path="/auth/callback" element={<AuthCallbackPage />} />
// 其余路由：
<Route path="/" element={<ProtectedRoute><Navigate to="/chat" /></ProtectedRoute>} />
<Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
// ... 以此类推
```

- [ ] **Step 3: TypeScript 检查**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

期望：无报错。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ProtectedRoute.tsx frontend/src/App.tsx
git commit -m "feat(auth): add ProtectedRoute, protect all routes"
```

---

## Task 13: Topbar 用户信息 + 退出登录

**Files:**
- Modify: `frontend/src/components/Topbar/Topbar.tsx`

- [ ] **Step 1: 读 Topbar.tsx 了解现有结构**

```bash
cat frontend/src/components/Topbar/Topbar.tsx
```

- [ ] **Step 2: 加 useMe hook 和 logout 按钮**

在 Topbar 组件里加：

```tsx
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { authStore } from "@/store/authStore";
import { useNavigate } from "react-router-dom";

// 组件内
const navigate = useNavigate();
const { data: me } = useSWR("/auth/me", (url) =>
  apiFetch(url).then((r) => r.json())
);

const logout = () => {
  authStore.clearTokens();
  navigate("/login", { replace: true });
};

// JSX：在 Topbar 右侧加
{me && (
  <div className="flex items-center gap-2">
    {me.avatar && (
      <img src={me.avatar} alt="" className="w-6 h-6 rounded-full" />
    )}
    <span className="text-[12px] text-[#888]">{me.name}</span>
    <button
      onClick={logout}
      className="text-[11.5px] text-[#555] hover:text-[#999] transition-colors"
    >
      退出
    </button>
  </div>
)}
```

- [ ] **Step 3: TypeScript 检查**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Topbar/Topbar.tsx
git commit -m "feat(auth): show user avatar and logout button in Topbar"
```

---

## 自检清单

- [x] GitHub OAuth：login → callback → JWT → 前端存储 → /chat
- [x] 飞书 OAuth：login → callback → JWT → 前端存储 → /chat
- [x] 未登录访问 /chat → 跳 /login
- [x] Token 过期 → refresh → 重试
- [x] Refresh token 过期 → 跳 /login
- [x] Threads 按 user_id 隔离
- [x] Tasks 按 user_id 隔离
- [x] /auth/* 不需要 Bearer token（公开）
- [x] 其余所有 API 需要 Bearer token

## Verification

```bash
# 后端验证
curl -s http://localhost:8000/api/threads/ | python3 -m json.tool  # 期望 401
curl -s http://localhost:8000/auth/github/login -v 2>&1 | grep -i location  # 期望 302 → GitHub

# 前端验证
# 1. 访问 http://localhost:5173/chat → 跳到 /login
# 2. 点 GitHub 登录 → 完成授权 → 回到 /chat
# 3. 刷新 → 还在 /chat（token 有效）
# 4. 清空 localStorage → 刷新 → 跳 /login
```
