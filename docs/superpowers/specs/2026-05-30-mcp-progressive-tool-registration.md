# MCP 工具渐进式注册机制 — 设计文档

**日期**：2026-05-30  
**状态**：草稿，待用户审阅  

---

## 背景与问题

使用 `langchain-mcp-adapters` 标准做法时，所有 MCP server 的完整工具 JSON schema 会一次性注入 agent 的工具列表和 system prompt。假设 3 个 server × 平均 10 个工具 = 30 个完整 schema，会造成：

- **Context 膨胀**：每个工具 schema 约 300-500 token，30 个工具约 1-1.5w token
- **LLM 选择困难**：工具列表过长导致选择不准确
- **冷启动慢**：每次启动需要连接所有 server 并加载所有工具

---

## 设计目标

1. Agent 的正式工具列表中只有**一个 MCP proxy 工具**（`mcp_call`）
2. MCP 工具的名称 + 简短描述以**紧凑文本**形式注入 system prompt（而非 JSON schema）
3. 执行时通过 middleware 路由到对应 MCP server
4. 每个工具的**审批策略**（auto / confirm / deny）在 DB 中配置，deny 的工具不出现在 context 里
5. 用户在 MCP 页面点击「发现工具」即可自动同步工具列表到 DB

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                       lifespan                          │
│  McpManager.start()                                     │
│   → 连接所有 enabled MCP server                          │
│   → 发现工具列表，同步到 DB tools_config                  │
│   → 缓存 {server → connection, tools} 在内存             │
└────────────────────────┬────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │    choreo_agent     │
              │  tools = [          │
              │    ...原有工具,      │
              │    mcp_call  ← 新增  │
              │  ]                  │
              │  middleware = [     │
              │    McpContextMW,   ← 注入紧凑目录
              │    McpApprovalMW,  ← 审批拦截
              │    ...原有中间件     │
              │  ]                  │
              └──────────────────────┘
```

---

## 三个核心组件

### 1. McpManager（`backend/choreo/mcp/manager.py`）

**职责**：管理 MCP server 连接生命周期，提供工具发现和调用能力。

```python
class McpManager:
    async def start(self)           # 连接所有 enabled server，发现工具，写回 DB
    async def reload(self)          # 重新连接（不重启进程），供 /api/mcp/reload 调用
    async def get_index(self) -> str        # 生成紧凑工具目录文字
    async def call(server, tool, args)      # 执行 MCP 工具调用
    async def shutdown(self)        # 关闭所有连接
```

**工具发现流程**：
```
连接 MCP server
  → list_tools() 获取工具列表
  → 对每个工具：
      if tool 已在 DB tools_config → 保留用户配置
      if tool 不在 DB → 写入 DB，默认 approval=confirm, enabled=true
  → 不在 server 里的旧工具 → 标记为 stale（不删除，保留配置）
```

**内存缓存格式**：
```python
{
  "github": {
    "conn": <MCPClient>,
    "tools": [
      {"name": "create_issue", "description": "Create a GitHub issue"},
      {"name": "search_code",  "description": "Search code in repositories"},
    ]
  },
  "postgres": { ... }
}
```

---

### 2. McpContextMiddleware（`backend/choreo/agents/middlewares/mcp_context.py`）

**职责**：在每次 LLM 调用前，将紧凑工具目录追加到 system prompt。

**模式**：与 `SkillsContextMiddleware` 完全相同，使用 `awrap_model_call`。

**注入内容**（仅显示 approval ≠ deny 的工具）：

```
Available MCP Tools (use mcp_call to invoke):

github:
  create_issue: Create a GitHub issue with title, body and labels
  search_code: Search code across repositories

postgres:
  query: Execute a SQL query and return results
  list_tables: List all tables in the database
```

**注入逻辑**：
```python
async def awrap_model_call(self, request, handler):
    index = await get_mcp_manager().get_index()  # 过滤掉 deny 的工具
    if index:
        existing = request.system_message.content if request.system_message else ""
        new_content = f"{existing}\n\n{index}"
        request = request.override(system_message=SystemMessage(content=new_content))
    return await handler(request)
```

---

### 3. mcp_call 工具（`backend/choreo/agents/tools/mcp_tool.py`）

**职责**：Agent 调用此工具时，代理到实际的 MCP server。

**工具 schema**（注入到 agent 的只有这一个）：

```python
@tool
async def mcp_call(server: str, tool: str, arguments: dict) -> str:
    """
    Call a tool on an MCP server.
    Args:
        server: MCP server name (from Available MCP Tools section)
        tool: Tool name to call
        arguments: Arguments dict for the tool
    """
    return await get_mcp_manager().call(server, tool, arguments)
```

---

### 4. McpApprovalMiddleware（`backend/choreo/agents/middlewares/mcp_approval.py`）

**职责**：拦截 `mcp_call` 的工具调用，根据 `tools_config` 执行审批逻辑。

**模式**：使用 `awrap_tool_call`。

```python
async def awrap_tool_call(self, request, handler):
    if request.tool_call["name"] != "mcp_call":
        return await handler(request)  # 非 MCP 工具直接放行
    
    args = request.tool_call["args"]
    server, tool = args["server"], args["tool"]
    
    cfg = await get_tool_config(server, tool)  # 从 DB 读取
    
    if cfg.approval == "deny":
        return ToolMessage(content=f"Tool {server}/{tool} is blocked.", ...)
    
    if cfg.approval == "confirm":
        # 触发 HITL 中断，展示 server + tool + arguments
        raise HumanInterruptRequired(action_request={
            "name": f"{server} · {tool}",
            "args": args["arguments"],  # 展示内层参数，不是外层的 mcp_call args
        })
    
    return await handler(request)  # auto → 直接执行
```

---

## 前端变更

### ReviewPanel — MCP 工具特殊渲染

当 `action.name` 包含 ` · `（server · tool 格式）时，特殊处理：

```
┌─────────────────────────────────────┐
│  🐙  github · create_issue          │
├─────────────────────────────────────┤
│  title   "Fix authentication bug"   │
│  body    "Steps to reproduce..."    │
│  labels  ["bug", "auth"]            │
├─────────────────────────────────────┤
│  ❯ Allow this action?   [No n] [Yes y] │
└─────────────────────────────────────┘
```

### ToolCallCard — MCP 工具图标

`mcp_call` 工具的卡片需要解析内层的 `server` 参数来显示对应图标：

```tsx
// 当 toolCall.name === "mcp_call" 时
const server = toolCall.args.server  // "github"
const innerTool = toolCall.args.tool  // "create_issue"
// 显示: 🐙 github · create_issue
```

### MCP 页面 — 工具发现按钮

「工具列表」Tab 顶部加「发现工具」按钮：
- 调用 `POST /api/mcp/reload` → 重新连接并发现工具
- 发现完成后刷新工具列表

---

## 新增 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/mcp/reload` | 重新加载 McpManager，重连所有 server，更新 DB tools_config |
| GET  | `/api/mcp/tools`  | 返回内存中已发现的工具列表（实时状态） |

---

## 文件清单

### 新建
```
backend/choreo/mcp/
  __init__.py          # get_mcp_manager() / set_mcp_manager()
  manager.py           # McpManager 类

backend/choreo/agents/
  tools/mcp_tool.py         # mcp_call @tool
  middlewares/mcp_context.py    # McpContextMiddleware
  middlewares/mcp_approval.py   # McpApprovalMiddleware
```

### 修改
```
backend/choreo/agents/choreo_agent.py   # 加入 mcp_call + 两个 middleware
backend/choreo/agents/middlewares/__init__.py  # 导出新 middleware
backend/choreo/gateway/app.py           # McpManager lifespan 集成
backend/choreo/gateway/routers/mcp.py  # 加 /reload 和 /tools 端点

frontend/src/components/ReviewPanel/ReviewPanel.tsx  # MCP 特殊渲染
frontend/src/components/Chat/ChatMessage.tsx          # mcp_call ToolCallCard
```

---

## 依赖

```toml
# backend/pyproject.toml 新增
"langchain-mcp-adapters>=0.1"
```

---

## 未考虑的范围（本版不做）

- MCP server 连接断开后的自动重连
- stdio 子进程崩溃检测
- 多 server 并发调用
- MCP 工具调用结果的流式返回

---

## 问题与风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| MCP server 启动慢（npm 冷启动） | lifespan 变慢 | 异步并发连接，超时 10s |
| server 连接失败 | 工具不可用 | 记录错误，跳过该 server，不阻塞启动 |
| tools_config 与实际工具不一致 | 审批配置失效 | reload 时同步，stale 工具标记展示 |
