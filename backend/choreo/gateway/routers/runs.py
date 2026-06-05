import asyncio
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from langchain_core.messages import AIMessageChunk
from choreo.models.run import RunInput
from choreo.agents import get_agent
from choreo.store.thread_store import thread_store
from choreo.agents.middlewares import pop_decision
from choreo.sandbox import get_sandbox_manager
from choreo.auth.deps import get_current_user_id

router = APIRouter()

RUN_QUEUES: dict[str, asyncio.Queue] = {}


def _serialize(obj):
    """将 LangChain / LangGraph 对象递归序列化为 JSON 兼容类型。"""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(i) for i in obj]
    if hasattr(obj, "model_dump"):
        try:
            return _serialize(obj.model_dump())
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return _serialize(obj.dict())
        except Exception:
            pass
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


@router.post("/{thread_id}/runs/stream")
async def stream_run(
    thread_id: str,
    body: RunInput,
    user_id: str = Depends(get_current_user_id),
):
    if not await thread_store.get(thread_id):
        raise HTTPException(404, "thread not found")

    run_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    RUN_QUEUES[run_id] = queue

    resume_decision = None
    if body.input is None:
        resume_decision = pop_decision(thread_id)

    context = body.context or {}
    context["user_id"] = user_id
    asyncio.create_task(_run_agent(run_id, thread_id, body.input, queue, resume_decision, context))

    return StreamingResponse(
        _read_queue(run_id, queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_agent(
    run_id: str,
    thread_id: str,
    inputs: dict | None,
    queue: asyncio.Queue,
    resume_decision: dict | None,
    context: dict | None = None,
):
    await queue.put({"event": "metadata", "data": {"run_id": run_id}})
    await thread_store.set_status(thread_id, "running")

    # Extract skill_context (not passed to agent configurable)
    skill_context = (context or {}).pop("skill_context", None) if context else None

    # If present, prepend to last user message
    if skill_context and inputs:
        messages = inputs.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict) and last_msg.get("role") == "user":
                original_content = last_msg.get("content", "") or ""
                if original_content:
                    last_msg["content"] = f"{skill_context}\n\n---\n\n{original_content}"
                else:
                    last_msg["content"] = skill_context

    config = {"configurable": {"thread_id": thread_id, **(context or {})}}

    if resume_decision is not None:
        run_input = Command(resume=resume_decision)
    else:
        messages = inputs.get("messages", []) if inputs else []
        run_input = {"messages": messages}

    try:
        async for chunk in get_agent().astream(
            run_input,
            config=config,
            stream_mode=["updates", "messages", "custom", "tasks", "values"],
            version="v2",
        ):
            chunk_type = chunk.get("type")
            data = chunk.get("data")

            # ── messages: LLM token 流 ──────────────────────────────
            if chunk_type == "messages":
                token, metadata = data

                # 只转发流式 chunk，过滤完整 AIMessage replay（否则内容会双发）
                if not isinstance(token, AIMessageChunk):
                    continue

                await queue.put({
                    "event": "messages",
                    "data": [{
                        "content": token.content,
                        "additional_kwargs": token.additional_kwargs or {},
                        "node": metadata.get("langgraph_node", ""),
                    }],
                })

            # ── updates: 节点状态变更 ───────────────────────────────
            elif chunk_type == "updates":
                if "__interrupt__" in data:
                    interrupts = data["__interrupt__"]
                    interrupt_payload = [
                        {"value": i.value if hasattr(i, "value") else i}
                        for i in interrupts
                    ]
                    await thread_store.set_status(thread_id, "interrupted")
                    await queue.put({
                        "event": "updates",
                        "data": {"__interrupt__": interrupt_payload},
                    })
                else:
                    # 普通节点状态变更（node_name → {state_diff}）
                    await queue.put({
                        "event": "updates",
                        "data": _serialize(data),
                    })

            # ── custom: 节点内 get_stream_writer() 发出的进度 ───────
            elif chunk_type == "custom":
                await queue.put({
                    "event": "custom",
                    "data": _serialize(data),
                })

            # ── tasks: 工具调用任务开始/结束 ────────────────────────
            elif chunk_type == "tasks":
                await queue.put({
                    "event": "tasks",
                    "data": _serialize(data),
                })
                # 新版 LangGraph HITL 中断走 tasks.interrupts 而非 updates.__interrupt__
                # 同时发一个 updates.__interrupt__ 保证前端标准处理路径生效
                if data.get("interrupts"):
                    await thread_store.set_status(thread_id, "interrupted")
                    interrupt_payload = [
                        {"value": i.get("value", {}) if isinstance(i, dict) else {}}
                        for i in data["interrupts"]
                    ]
                    await queue.put({
                        "event": "updates",
                        "data": {"__interrupt__": interrupt_payload},
                    })

            # ── values: 每步执行后的完整 state 快照 ─────────────────
            elif chunk_type == "values":
                await queue.put({
                    "event": "values",
                    "data": _serialize(data),
                })

    except Exception as e:
        await queue.put({"event": "error", "data": {"message": str(e)}})
    finally:
        state = await thread_store.get(thread_id)
        if state and state.status == "running":
            await thread_store.set_status(thread_id, "idle")
        await get_sandbox_manager().release(thread_id)

        # Trigger background skill review (only on real user messages, not HITL resume)
        review_started = False
        if not isinstance(run_input, Command):
            try:
                from choreo.skills.review_worker import extract_invoked_skills, maybe_start_review, evaluate_for_suggestion
                agent_state = await get_agent().aget_state(config)
                final_messages = agent_state.values.get("messages", [])
                invoked_skills = extract_invoked_skills(final_messages)

                # 快速评估是否值得建议保存为新技能（5s 超时）
                try:
                    suggestion = await asyncio.wait_for(
                        evaluate_for_suggestion(final_messages), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    suggestion = None

                if suggestion:
                    # 持久化 suggestion，供切换线程后仍可查看
                    import time as _time
                    from choreo.db import SkillSuggestionRow, SessionLocal
                    async with SessionLocal() as sess:
                        # 覆盖同线程的旧建议（每线程只保留最新一条）
                        from sqlalchemy import delete
                        await sess.execute(
                            delete(SkillSuggestionRow).where(SkillSuggestionRow.thread_id == thread_id)
                        )
                        sess.add(SkillSuggestionRow(
                            thread_id=thread_id,
                            category=suggestion["category"],
                            name=suggestion["name"],
                            description=suggestion["description"],
                            content=suggestion["content_draft"],
                            created_at=int(_time.time()),
                        ))
                        await sess.commit()
                    await queue.put({"event": "skill_suggestion", "data": suggestion})

                review_started = await maybe_start_review(thread_id, final_messages, invoked_skills)
            except Exception:
                pass  # Never crash SSE over review failure

        await queue.put({"event": "updates", "data": {"__review_started__": review_started}})
        await queue.put(None)


async def _read_queue(run_id: str, queue: asyncio.Queue):
    while True:
        item = await queue.get()
        if item is None:
            RUN_QUEUES.pop(run_id, None)
            yield f"event: end\ndata: {{}}\n\n"
            break
        event = item["event"]
        data = json.dumps(item["data"], ensure_ascii=False)
        yield f"event: {event}\ndata: {data}\n\n"
