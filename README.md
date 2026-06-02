<div align="center">

# 🎼 Choreo

**一个越用越懂你的开发自动化伙伴。**

你用一句话交代杂活，Choreo 写出脚本、让你确认、定时执行——
更重要的是，它会**记住你的偏好**，并把每次任务沉淀成**可复用、会自我进化的技能**。

用得越久，它越强。

[快速开始](#-快速开始) · [核心亮点](#-核心亮点) · [架构](#-架构) · [路线图](#-路线图)

</div>

---

## 💡 它解决什么问题

开发者每天有一堆**单调、重复、不难、但每次都要手动花十几分钟**的杂活：整理 PR 周报、汇总 commit 成 changelog、巡检依赖漏洞、CI 失败告警……

大多数 AI 工具能帮你做**一次**，但做完就忘了——下次你还得从头解释。Choreo 不一样：它**记得**，并且**会成长**。

## ⭐ 核心亮点

Choreo 的设计理念受 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 启发，但用 **React + LangChain** 重新实现，并聚焦于「开发杂活自动化」这一垂直场景。它有四个让它与众不同的支柱：

### 📈 技能会自我进化

Choreo 不是一个静态的脚本生成器，而是一套**会学习的技能系统**：

- **自主沉淀**：当 agent 完成一个较复杂的任务（多次工具调用）后，会把"这类事该怎么做"自动整理成一份可复用的**技能文档**。
- **使用中修补**：技能在被调用时，如果发现它过时、不完整或出了错，Choreo 会就地修正它——技能因此越用越准。
- **自动策展**：一个后台策展器会定期审查所有技能，合并重叠的、归档陈旧的、保护你手动锁定（pin）的，让技能库始终保持精炼。

> 结果是：你教 Choreo 做过一次"标准周报"，它就永远会做，而且会越做越符合你的口味。

### 🧠 可扩展的记忆系统

Choreo 跨会话记住对你重要的东西，而不是每次都失忆：

- **两层记忆**：`USER.md` 记录你的偏好（"周报用 markdown 表格"），`MEMORY.md` 记录项目事实与上下文——都是**人类可读、可手动编辑**的文件。
- **可搜索的历史**：基于全文检索 + LLM 摘要，几周后回到一个项目，Choreo 能主动唤起相关的历史上下文，不用你重新解释。
- **可插拔后端**：内置记忆层开箱即用，也可接入更强的记忆 provider 插件，按需升级。

### 🔍 产物是代码，不是黑箱

很多 AI 工具帮你干活时你看不见过程。**Choreo 给你的是一段你能读懂的 Python 脚本**——能看、能改、能存、能纳入 git。透明可控，是开发者敢用它的前提。

### 🛡 人在回路，安全可控

任何「写操作」（执行脚本、发消息、改文件）默认会**暂停并等你确认**。你可以批准、改一改再放行、或直接拒绝。Choreo 永远不会在你不知情时动你的东西。

## 🎬 一个完整的故事

```
你（网页输入）: 每周五 17:00 把这周的 commit 整理成更新日志草稿发我飞书
        │
Choreo:  我理解了。我记得你上次说过 changelog 要按 feat/fix 分组——
         这是我写好的脚本 👇  [展示完整脚本，语法高亮]
        │
你:      看了一眼，没问题 → 点「确认」✅
        │
Choreo:  已设为每周五 17:00 自动运行。
         同时我把「生成 changelog」沉淀成了一个技能，下次直接复用。
        │
（几周后，你换了个新仓库）
你:      给这个项目也来份 changelog
Choreo:  好，直接套用之前的技能 + 你的分组偏好，3 秒生成 👍
```

## 🚀 快速开始

### 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | >= 3.10 | 后端 |
| [uv](https://docs.astral.sh/uv/) | 最新 | Python 包管理 |
| Node.js | >= 18 | 前端 |
| [pnpm](https://pnpm.io/) | >= 8 | 前端包管理 |
| PostgreSQL | >= 14 | 会话 / 历史持久化 |
| Docker（可选） | >= 24 | AIO Sandbox 沙箱 |

### 1. 克隆仓库

```bash
git clone https://github.com/your-name/choreo.git
cd choreo
```

### 2. 配置

```bash
# 复制配置模板
cp backend/config.example.yaml backend/config.yaml
cp backend/.env.example backend/.env
```

编辑 `backend/config.yaml`，填入模型信息：

```yaml
active_model: deepseek-chat   # 改成你要用的模型名

models:
  - name: deepseek-chat
    use: choreo.models.patched_openai:PatchedChatOpenAI
    model: deepseek-chat
    api_key: sk-your-api-key      # 填入真实 key
    base_url: https://api.deepseek.com/v1
```

编辑 `backend/.env`，填入数据库和其他密钥：

```ini
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/choreo
LANGSMITH_API_KEY=          # 可选，用于 trace

# 飞书 Bot（可选，见下方「接入飞书」）
FEISHU_ENABLED=false
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_NOTIFY_CHAT_ID=      # 可选，agent 主动推送通知的目标 chat_id

# 邮件通知（可选）
SMTP_HOST=smtp.qq.com       # QQ邮箱示例，163用 smtp.163.com
SMTP_PORT=465
SMTP_USER=yourname@qq.com
SMTP_PASSWORD=              # 授权码，非登录密码
```

### 3. 启动后端

```bash
cd backend
uv sync                     # 安装依赖
uv run uvicorn choreo.gateway.app:app --reload --port 8009
```

后端启动后访问 `http://localhost:8009/docs` 可查看 API 文档。

### 4. 启动前端

```bash
# 另开一个终端
cd frontend
pnpm install
pnpm dev
```

打开 `http://localhost:5173`，输入第一条指令。

### 5. 接入飞书（可选）

在[飞书开放平台](https://open.feishu.cn/app)创建企业自建应用，开通 `im:message` 权限并添加「机器人」能力，然后：

1. 在「事件订阅」选择「使用长连接接收事件」，订阅「接收消息」事件
2. 填入 `.env`：
   ```ini
   FEISHU_ENABLED=true
   FEISHU_APP_ID=cli_xxxxxxxx
   FEISHU_APP_SECRET=xxxxxxxx
   ```
3. 在 `backend/config.yaml` 中启用：
   ```yaml
   platforms:
     - name: feishu
       transport: websocket
   ```
4. 发布应用，在飞书里搜索应用名称即可对话

飞书对话支持所有 agent 能力，工具调用全部自动确认，无需手动审批。发送 `/new` 开启新对话。

> **通知推送**：配置 `FEISHU_NOTIFY_CHAT_ID` 后，agent 可主动向你的飞书私聊发通知（如定时任务完成、异常告警等）。首次与 Bot 对话后 chat_id 会自动记录到数据库，可通过 `SELECT chat_id FROM channels WHERE platform='feishu'` 查询。

### 6. 配置邮件通知（可选）

配置后 agent 可通过 `send_notification(channel="email")` 发邮件给你：

```ini
# backend/.env
SMTP_HOST=smtp.qq.com       # QQ邮箱；163邮箱用 smtp.163.com
SMTP_PORT=465
SMTP_USER=yourname@qq.com
SMTP_PASSWORD=xxxx          # 授权码（非登录密码）
                             # QQ邮箱：设置 → 账户 → 开启SMTP → 生成授权码
```

### 7. 配置沙箱（可选）

Choreo 使用 [AIO Sandbox](https://github.com/agent-infra/sandbox) 在隔离环境中执行代码。沙箱是**懒加载**的——只有 agent 实际调用文件/命令工具时才会启动容器，纯对话不会触发。

**默认模式（aios-local）**：需要本地 Docker，后端会自动为每个对话线程创建独立容器：

```yaml
# backend/config.yaml
active_sandbox: aios-local

sandboxes:
  - name: aios-local
    provider: aios
    image: enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox
    workspace_dir: /home/gem
    timeout: 60
    auto_start: true
    idle_timeout: 300   # 闲置 5 分钟后自动销毁容器
```

**无 Docker 模式**：改为 `active_sandbox: local-dev`，直接在本地文件系统的 `./sandbox` 目录操作，无沙箱隔离。

**沙箱目录约定**：

| 目录 | 用途 |
|------|------|
| `work/` | 过程文件：临时脚本、中间结果（可清理）|
| `output/` | 最终产物：报告、生成代码（可在「输出目录」页面预览下载）|
| `uploads/` | 用户上传素材（只读）|

## 🏗 架构

后端是核心——一个基于 LangChain `create_agent` 的智能体，外加记忆、技能、调度、沙箱四个子系统；前端是与之对话、审阅脚本、管理技能与记忆的界面。

```
┌───────────────────────┐        ┌─────────────────────────────────────────┐
│   前端 (React + Vite)  │        │         后端 (FastAPI + LangChain)        │
│                       │  HTTP  │                                          │
│  · 对话输入            │ ─────▶ │  create_agent 智能体 (ReAct 循环)         │
│  · 脚本审阅 / 确认     │ ◀───── │   ├─ tools: 读git / 生成脚本 / 执行 / 通知 │
│  · 技能库管理 & pin    │  SSE   │   ├─ middleware: 人在回路 + 调用上限        │
│  · 记忆查看 / 编辑     │        │   └─ checkpointer: 中断/恢复               │
│  · 运行历史 & 产物     │        │                                          │
└───────────────────────┘        │  🧠 记忆: USER.md + MEMORY.md + 历史检索   │
                                 │  📈 技能: 自主沉淀 / 使用中修补 / 策展      │
                                 │  ⏰ 调度: APScheduler 定时跑               │
                                 │  📦 沙箱: 隔离执行生成的脚本               │
                                 └─────────────────────────────────────────┘
                                              ▲
                                 ┌────────────┴────────────┐
                                 │  💬 聊天平台 (可插拔)     │
                                 │  · 飞书 WebSocket/Webhook │
                                 │  · 可扩展更多平台          │
                                 └─────────────────────────┘
```

### 为什么用 `create_agent` + 中间件

Choreo 的「写操作前必须人工确认」由 LangChain 的 `HumanInTheLoopMiddleware` 原生支持：声明哪些工具需拦截，agent 就会在调用前暂停、保存状态、等前端确认后从断点恢复。底层由 LangGraph 的 checkpointer 驱动，无需自建状态机。技能与记忆系统则作为 agent 的上下文注入与工具，参与每一次决策。

## 🧩 扩展性

Choreo 的能力是「内生可扩展」的，三个层级，门槛由高到低：

| 层级 | 是什么 | 谁能加 | 例子 |
|---|---|---|---|
| **Tool** | 一个原子能力 | 开发者（写 Python） | `send_feishu` |
| **Skill** | 一类任务的做法 | **任何人（写 markdown）** | "如何生成周报" |
| **Plugin** | 打包的能力集 | 开发者 | "企业微信插件" |

> **Skill 是降低贡献门槛的关键**——不会写代码？写个 markdown 就能教 Choreo 一个新技能。而技能一旦沉淀，还会自我进化。

## 🗺 路线图

- [x] 核心 agent：读 git → 生成脚本 → 沙箱执行 → 通知
- [x] 人在回路：写操作前确认（键盘快捷键 y/n）
- [x] 记忆系统：USER.md / MEMORY.md + 历史检索
- [x] 技能系统：自主沉淀 + 使用中修补
- [x] 飞书 Bot：WebSocket 长连接，直接在飞书对话
- [x] 可插拔聊天平台层（新增平台只需一个文件）
- [x] 技能策展器：后台定期自动合并重复 / 归档过时技能
- [x] 沙箱隔离：per-thread Docker 容器，懒加载按需启动
- [x] 输出目录浏览器：文件预览（图片/Markdown/代码）+ 下载
- [x] 对话历史页面：列表展示所有线程，点击继续对话
- [x] 多模型选择器：每条消息可指定不同模型
- [x] MCP 工具集成：可视化配置 MCP Server 和工具审批
- [ ] 技能市场（社区共享与一键安装）
- [ ] GitHub Webhook 触发
- [ ] 可插拔记忆 provider
- [ ] 飞书 HITL 交互卡片（按钮确认）
- [ ] 云端沙箱（Daytona 支持）

## 🙏 致谢

核心理念深受 [NousResearch / Hermes Agent](https://github.com/NousResearch/hermes-agent) 的「记忆 + 技能 + 自我进化」架构启发。Choreo 在此基础上聚焦开发场景，并采用 React + LangChain 技术栈重新实现。

## 📄 License

[MIT](LICENSE)

---

<div align="center">
<sub>Choreo —— 越用越懂你的开发自动化伙伴。🎼</sub>
</div>
