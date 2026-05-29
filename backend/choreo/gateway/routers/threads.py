from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, AIMessage
from choreo.models.thread import Thread, ThreadState
from choreo.models.run import StateUpdate
from choreo.store.thread_store import thread_store
from choreo.agents.middlewares import store_decision
from choreo.agents import get_agent

router = APIRouter()


@router.get("/", response_model=list[ThreadState])
async def list_threads():
    return await thread_store.list_all()


@router.post("/", response_model=Thread, status_code=201)
async def create_thread():
    thread = Thread()
    await thread_store.save(thread)
    return thread


@router.get("/{thread_id}/state", response_model=ThreadState)
async def get_thread_state(thread_id: str):
    state = await thread_store.get(thread_id)
    if not state:
        raise HTTPException(404, "thread not found")
    return state


@router.post("/{thread_id}/state")
async def update_thread_state(thread_id: str, body: StateUpdate):
    if not await thread_store.get(thread_id):
        raise HTTPException(404, "thread not found")
    store_decision(thread_id, body.values)
    return {"ok": True}


@router.get("/{thread_id}/messages")
async def get_thread_messages(thread_id: str):
    if not await thread_store.get(thread_id):
        raise HTTPException(404, "thread not found")

    config = {"configurable": {"thread_id": thread_id}}
    state = await get_agent().aget_state(config)

    result = []
    for msg in (state.values.get("messages", []) if state.values else []):
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": str(msg.content)})
        elif isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, list):
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
                thinking = "".join(
                    b.get("thinking", "") or b.get("reasoning", "")
                    for b in content if b.get("type") in ("thinking", "reasoning")
                )
                if text:
                    result.append({"role": "assistant", "content": text, "thinking": thinking or None})
            elif content:
                result.append({"role": "assistant", "content": str(content)})

    return result
