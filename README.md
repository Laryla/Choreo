<div align="center">

# 🎼 Choreo

**用一句话，把重复的开发杂活变成会自动跑的脚本。**

你说"每周五把这周的 commit 整理成更新日志发我飞书"，Choreo 听懂、写出脚本、让你确认、然后定时执行——产物是你看得懂的代码，不是黑箱操作。

[快速开始](#-快速开始) · [它能做什么](#-它能做什么) · [架构](#-架构) · [路线图](#-路线图)

</div>

---

## 💡 它解决什么问题

开发者每天有一堆**单调、重复、不难、但每次都要手动花十几分钟**的杂活：

- 把本周 merge 的 PR 整理成周报
- 发版前把一堆 commit 汇总成 changelog 草稿
- 定期巡检几个仓库的依赖漏洞
- CI 挂了第一时间收到摘要 + 可能原因

它们卡在"懒得做"和"不得不做"之间，又不值得专门写脚本维护。Choreo 就是来吃掉这些杂活的。

## ✨ 它和别的工具不一样的地方

很多 AI 工具是**黑箱**——你让它干活，它在后台帮你点点点，但你看不见它做了什么，出错也不知道哪错了。

**Choreo 给你的是一段你能读懂的代码。** 你能看、能改、能存下来下次直接复用，也能在它执行任何"写操作"前喊停。对开发者来说，这种**透明可控**比"全自动黑箱"更让人放心。

## 🎬 它能做什么

```
你（在网页里输入）: 每周五 17:00 把这周的 commit 整理成更新日志草稿发我飞书
        │
Choreo:  我理解了，这件事需要读 git 记录、整理成文档、发飞书。
         这是我写好的脚本 👇
         ┌─────────────────────────────┐
         │  # generate_changelog.py     │
         │  import subprocess ...       │   ← 你能完整看到
         └─────────────────────────────┘
        │
你:      看了一眼，没问题 → 点「确认」✅
        │
Choreo:  已设为每周五 17:00 自动运行。
        │
（每周五到点）
Choreo:  📄 更新日志草稿已生成，发你飞书了。
```

## 🚀 快速开始

### 环境要求

- Node.js >= 18（前端）
- Python >= 3.10（后端）
- 已安装并登录 [`gh` CLI](https://cli.github.com/)（用于读取 PR / issue）

### 1. 克隆并安装

```bash
git clone https://github.com/your-name/choreo.git
cd choreo

# 后端
cd backend
pip install -e .

# 前端
cd ../frontend
npm install
```

### 2. 配置

复制后端的环境变量模板并填写：

```bash
cd backend
cp .env.example .env
```

```ini
# LLM（OpenAI 兼容接口，可接 deepseek）
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
CHOREO_MODEL=deepseek-chat

# 通知
FEISHU_WEBHOOK_URL=
SMTP_HOST=
SMTP_USER=
SMTP_PASSWORD=

# 沙箱
CHOREO_SANDBOX_TIMEOUT=120
```

### 3. 启动

```bash
# 终端 1：后端 API
cd backend
uvicorn choreo.api:app --reload --port 8000

# 终端 2：前端
cd frontend
npm run dev
```

打开 `http://localhost:5173`，输入你的第一条指令试试。

## 🏗 架构

Choreo 分前后端两部分。后端是核心——一个基于 LangChain `create_agent` 的智能体；前端是与之对话、审阅脚本、管理定时任务的界面。

```
┌────────────────────────┐         ┌──────────────────────────────────────┐
│   前端 (React + Vite)   │         │          后端 (FastAPI + LangChain)    │
│                        │  HTTP   │                                       │
│  · 对话输入框           │ ──────▶ │  create_agent 智能体                   │
│  · 脚本审阅 / 确认面板   │ ◀────── │   ├─ tools: 读git / 生成脚本 /          │
│  · 定时任务管理         │  SSE    │   │         执行脚本 / 发通知            │
│  · 运行历史 & 产物预览   │         │   ├─ middleware:                       │
│                        │         │   │    · HumanInTheLoop（写操作前暂停） │
└────────────────────────┘         │   │    · ModelCallLimit（防失控）       │
                                   │   └─ checkpointer（中断/恢复状态）      │
                                   │                                       │
                                   │  调度器 (APScheduler) — 定时跑任务      │
                                   │  沙箱 — 隔离执行生成的脚本              │
                                   └──────────────────────────────────────┘
```

### 后端：为什么用 `create_agent` + 中间件

Choreo 的核心安全设计是「执行脚本 / 发通知这类写操作前，必须由人确认」。LangChain 的 `HumanInTheLoopMiddleware` 正好原生支持这点——只需声明哪些工具需要拦截，agent 就会在调用它们前暂停、保存状态、等你在前端点确认后从断点恢复。底层由 LangGraph 的 checkpointer 驱动，无需自己造状态机。

智能体被赋予四个工具，由模型自主编排调用顺序：

| 工具 | 作用 | 是否需确认 |
|---|---|---|
| `read_git_log` | 读取 commit / PR / issue | 否（只读） |
| `generate_script` | 生成 Python 脚本并落盘到 `tasks/` | 否 |
| `run_script` | 在沙箱中执行脚本 | ✅ 是 |
| `send_notification` | 发送邮件 / 飞书 | ✅ 是 |

确认环节支持三种决策：**批准**原样执行、**编辑**参数后执行、**拒绝**并反馈。

### 前端：React 负责什么

前端不只是聊天框，它围绕「人在回路」这个核心体验设计：

- **对话区**：输入自然语言指令，流式看到 agent 的思考与工具调用
- **审阅面板**：当 agent 想执行脚本时，这里展示完整脚本（语法高亮），并提供「确认 / 编辑 / 拒绝」按钮——这是 Choreo 透明可控理念的落点
- **定时任务**：把指令注册成 cron 任务，查看 / 暂停 / 删除
- **运行历史**：每次执行的产物（周报、changelog 文件）可在线预览

## 🔐 安全

- 生成的脚本默认在**受限沙箱**中执行（超时限制、工作目录隔离）。生产环境建议替换为 Docker / gVisor 做更强隔离。
- 所有「写操作」默认触发人工确认，不会在你不知情时改动任何东西。
- 每段生成的脚本都落盘到 `tasks/`，可审计、可纳入 git 版本管理。

## 🧰 技术栈

**前端**：React · Vite · TypeScript · TailwindCSS

**后端**：Python · FastAPI · LangChain（`create_agent` + middleware）· LangGraph runtime · APScheduler

**LLM**：任意 OpenAI 兼容接口（默认 deepseek）

## 🗺 路线图

- [x] 核心 agent：读 git → 生成脚本 → 沙箱执行 → 通知
- [x] 人在回路：写操作前确认
- [x] CLI / 网页两种入口
- [ ] GitHub Webhook 触发（PR merge 自动生成 changelog 等）
- [ ] 脚本模板市场（社区共享常用自动化）
- [ ] 更强沙箱（Docker 隔离）
- [ ] 多 LLM 切换与成本统计

## 🤝 贡献

欢迎 issue 和 PR！如果你有「每天都要手动做、特别想自动化」的开发杂活场景，也欢迎在 Discussions 里分享，这是 Choreo 最好的需求来源。

## 📄 License

[MIT](LICENSE)

---

<div align="center">
<sub>Choreo —— 让琐碎的开发杂活，编排成自动运行的乐章。🎼</sub>
</div>
