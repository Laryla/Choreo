"""
LangSmith agent 评估测试。

使用方式：
  # 单次运行（结果上报到 LangSmith）
  uv run pytest tests/test_agent_langsmith.py -v

  # 指定项目名
  LANGSMITH_PROJECT=choreo-prod uv run pytest tests/test_agent_langsmith.py -v

所有测试结果可在 https://smith.langchain.com 查看 trace 和评分。
"""
import os
import asyncio
import uuid
import pytest
from langsmith import evaluate, Client
from langsmith.schemas import Example, Run
from langgraph.checkpoint.memory import InMemorySaver


# ── 工具函数 ─────────────────────────────────────────────────────────

def _run_agent(agent, messages: list[dict], thread_id: str | None = None) -> dict:
    """同步包装器：运行 agent，返回最后一条 AI 消息内容。
    使用 asyncio.run() 保证在任意线程（包括 evaluate() 的线程池）中都能正常运行。
    """
    tid = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": tid}}

    async def _invoke():
        result = await agent.ainvoke(
            {"messages": messages},
            config=config,
        )
        ai_msgs = [m for m in result["messages"] if hasattr(m, "content") and m.type == "ai"]
        return {"output": ai_msgs[-1].content if ai_msgs else "", "messages": result["messages"]}

    return asyncio.run(_invoke())


def _make_agent():
    """创建测试专用 agent：用 InMemorySaver，移除需要 PostgreSQL 的 TitleMiddleware。"""
    from langchain.agents import create_agent
    from langchain.agents.middleware import HumanInTheLoopMiddleware
    from choreo.model_factory import load_model
    from choreo.agents.tools import read_git_log, send_notification, read_file, write_file, edit_file, list_dir, grep, bash
    from choreo.agents.middlewares import ModelCallLimitMiddleware, ModelSelectorMiddleware

    return create_agent(
        model=load_model(),
        tools=[read_git_log, send_notification, read_file, write_file, edit_file, list_dir, grep, bash],
        system_prompt=(
            "你是 Choreo，一个开发自动化 Agent。\n"
            "你有以下工具：read_git_log、read_file、write_file、edit_file、list_dir、grep、bash、send_notification。\n"
            "修改文件前先用 read_file 了解内容；执行 bash 命令和发送通知前必须等用户确认。"
        ),
        middleware=[
            ModelSelectorMiddleware(),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "bash": {"description": "即将执行 bash", "allowed_decisions": ["approve", "edit", "reject"]},
                    "send_notification": {"description": "即将发送通知", "allowed_decisions": ["approve", "reject"]},
                }
            ),
            ModelCallLimitMiddleware(max_calls=10),
            # 不含 TitleMiddleware（避免测试环境 PostgreSQL 依赖）
        ],
        checkpointer=InMemorySaver(),
    )


# ── 评估器 ────────────────────────────────────────────────────────────

def contains_keywords(outputs: dict, reference_outputs: dict) -> dict:
    """检查输出中是否包含期望关键词（不区分大小写）。"""
    keywords: list[str] = reference_outputs.get("keywords", [])
    output: str = str(outputs.get("output", "")).lower()
    matched = sum(1 for kw in keywords if kw.lower() in output)
    score = matched / len(keywords) if keywords else 1.0
    return {"score": score, "comment": f"匹配 {matched}/{len(keywords)} 个关键词"}


def tool_was_called(outputs: dict, reference_outputs: dict) -> dict:
    """检查期望的工具是否被调用过。"""
    expected_tool: str = reference_outputs.get("expected_tool", "")
    if not expected_tool:
        return {"score": 1.0, "comment": "无需工具调用"}
    messages = outputs.get("messages", [])
    tool_names = [
        tc["name"]
        for m in messages
        if hasattr(m, "tool_calls") and m.tool_calls
        for tc in m.tool_calls
    ]
    called = expected_tool in tool_names
    return {
        "score": 1.0 if called else 0.0,
        "comment": f"期望工具 {expected_tool!r}，实际调用: {tool_names}",
    }


def response_not_empty(outputs: dict, reference_outputs: dict) -> dict:
    """检查 agent 有实质性回复（不为空）。"""
    output = str(outputs.get("output", "")).strip()
    score = 1.0 if len(output) > 10 else 0.0
    return {"score": score, "comment": f"回复长度: {len(output)} 字符"}


# ── Dataset 构建 ──────────────────────────────────────────────────────

DATASET_NAME = "choreo-agent-eval"

TEST_CASES = [
    # (name, inputs, reference_outputs)
    (
        "basic_greeting",
        {"messages": [{"role": "user", "content": "你好，你是谁？能做什么？"}]},
        {"keywords": ["choreo", "自动化", "工具"], "expected_tool": ""},
    ),
    (
        "list_tools",
        {"messages": [{"role": "user", "content": "你有哪些工具可以使用？"}]},
        {"keywords": ["read_file", "bash", "grep"], "expected_tool": ""},
    ),
    (
        "read_git_log",
        {"messages": [{"role": "user", "content": "帮我看一下最近一周的 git commit"}]},
        {"keywords": ["commit", "git"], "expected_tool": "read_git_log"},
    ),
    (
        "read_file_intent",
        {"messages": [{"role": "user", "content": "读取 README.md 文件的内容"}]},
        {"keywords": [], "expected_tool": "read_file"},
    ),
    (
        "list_dir_intent",
        {"messages": [{"role": "user", "content": "列出当前目录下的所有文件"}]},
        {"keywords": [], "expected_tool": "list_dir"},
    ),
    (
        "grep_intent",
        {"messages": [{"role": "user", "content": "在代码里搜索所有包含 'def create' 的地方"}]},
        {"keywords": [], "expected_tool": "grep"},
    ),
    (
        "multi_turn",
        {
            "messages": [
                {"role": "user", "content": "帮我列一下项目目录"},
                {"role": "assistant", "content": "好的，我来列出当前目录..."},
                {"role": "user", "content": "有没有 Python 文件？"},
            ]
        },
        {"keywords": [], "expected_tool": "grep"},
    ),
    (
        "bash_requires_confirm",
        {"messages": [{"role": "user", "content": "执行 ls -la 命令"}]},
        {"keywords": [], "expected_tool": "bash"},
    ),
]


def ensure_dataset(client: Client) -> str:
    """确保 LangSmith 上有测试数据集，没有则创建。"""
    try:
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        return ds.id
    except Exception:
        pass

    ds = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Choreo agent 功能评估数据集",
    )
    client.create_examples(
        inputs=[tc[1] for tc in TEST_CASES],
        outputs=[tc[2] for tc in TEST_CASES],
        metadata=[{"name": tc[0]} for tc in TEST_CASES],
        dataset_id=ds.id,
    )
    return ds.id


# ── 测试入口 ──────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.getenv("LANGSMITH_API_KEY"),
    reason="需要设置 LANGSMITH_API_KEY",
)
def test_agent_evaluate():
    """
    使用 LangSmith evaluate() 对 agent 全量评估。
    结果上报到 LangSmith，可在 smith.langchain.com 查看。
    """
    client = Client()
    ensure_dataset(client)
    agent = _make_agent()

    def target(inputs: dict) -> dict:
        return _run_agent(agent, inputs["messages"])

    results = evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[contains_keywords, tool_was_called, response_not_empty],
        experiment_prefix="choreo-agent",
        metadata={"version": "sandbox-tools"},
        max_concurrency=1,  # agent 有内部状态，串行更安全
    )

    # 汇总分数：row 是 dict，row["evaluation_results"]["results"] 是 EvaluationResult 列表
    scores = {}
    for row in results:
        for ev in row["evaluation_results"]["results"]:
            scores.setdefault(ev.key, []).append(ev.score)

    print("\n── 评估结果摘要 ──")
    for key, vals in scores.items():
        valid = [v for v in vals if v is not None]
        avg = sum(valid) / len(valid) if valid else 0.0
        print(f"  {key}: {avg:.2f} (n={len(vals)})")

    # 核心指标：response_not_empty 平均分必须 >= 0.8
    empty_scores = [v for v in scores.get("response_not_empty", []) if v is not None]
    avg_not_empty = sum(empty_scores) / len(empty_scores) if empty_scores else 0.0
    assert avg_not_empty >= 0.8, f"agent 回复率过低: {avg_not_empty:.2f}"


@pytest.mark.skipif(
    not os.getenv("LANGSMITH_API_KEY"),
    reason="需要设置 LANGSMITH_API_KEY",
)
def test_single_trace():
    """
    单条 trace 测试：验证 agent 能正常响应，trace 上报到 LangSmith。
    """
    agent = _make_agent()
    result = _run_agent(
        agent,
        [{"role": "user", "content": "你好，简单介绍一下你自己"}],
    )
    output = result["output"]
    assert len(output) > 0, "agent 没有回复"
    print(f"\n回复: {output[:200]}")
