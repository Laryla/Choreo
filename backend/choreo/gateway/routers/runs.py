import asyncio
import json
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from langchain_core.messages import AIMessageChunk
from choreo.models.run import RunInput
from choreo.agents import get_agent
from choreo.store.thread_store import thread_store
from choreo.agents.middlewares import pop_decision

router = APIRouter()

RUN_QUEUES: dict[str, asyncio.Queue] = {}


@router.post("/{thread_id}/runs/stream")
async def stream_run(thread_id: str, body: RunInput):
    if not await thread_store.get(thread_id):
        raise HTTPException(404, "thread not found")

    run_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    RUN_QUEUES[run_id] = queue

    resume_decision = None
    if body.input is None:
        resume_decision = pop_decision(thread_id)

    asyncio.create_task(_run_agent(run_id, thread_id, body.input, queue, resume_decision, body.context))

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
    from choreo.sandbox import get_sandbox_manager
    await queue.put({"event": "metadata", "data": {"run_id": run_id}})
    await thread_store.set_status(thread_id, "running")

    # acquire sandbox（懒加载，sandbox 在工具调用时也会自动 acquire，这里提前初始化）
    sandbox_name = (context or {}).get("sandbox_name")
    await get_sandbox_manager().acquire(thread_id, sandbox_name)

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
            stream_mode=["updates", "messages"],
            version="v2",
        ):
            chunk_type = chunk.get("type")
            data = chunk.get("data")

            if chunk_type == "messages":
                token, _ = data

                # 只处理流式 chunk，过滤掉 LangGraph 在 model 节点结束后
                # 再次发出的完整 AIMessage（否则内容会重复发送两次）
                if not isinstance(token, AIMessageChunk):
                    continue

                await queue.put({
                    "event": "messages",
                    "data": [{
                        "content": token.content,
                        "additional_kwargs": token.additional_kwargs or {},
                    }],
                })

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

    except Exception as e:
        await queue.put({"event": "error", "data": {"message": str(e)}})
    finally:
        state = await thread_store.get(thread_id)
        if state and state.status == "running":
            await thread_store.set_status(thread_id, "idle")
        await get_sandbox_manager().release(thread_id)
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
