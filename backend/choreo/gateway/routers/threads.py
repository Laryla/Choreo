from fastapi import APIRouter, HTTPException, Depends
from langchain_core.messages import HumanMessage, AIMessage
from choreo.models.thread import Thread, ThreadState
from choreo.models.run import StateUpdate
from choreo.store.thread_store import thread_store
from choreo.agents.middlewares import store_decision
from choreo.agents import get_agent
from choreo.auth.deps import get_current_user_id
from choreo.db import SessionLocal, ThreadRow

router = APIRouter()


async def _assert_thread_owned(thread_id: str, user_id: str) -> None:
    async with SessionLocal() as db:
        row = await db.get(ThreadRow, thread_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "thread not found")


@router.get("/", response_model=list[ThreadState])
async def list_threads(user_id: str = Depends(get_current_user_id)):
    return await thread_store.list_by_user(user_id)


@router.post("/", response_model=Thread, status_code=201)
async def create_thread(user_id: str = Depends(get_current_user_id)):
    thread = Thread()
    await thread_store.create_for_user(thread.thread_id, user_id)
    return thread


@router.get("/{thread_id}/state", response_model=ThreadState)
async def get_thread_state(thread_id: str, user_id: str = Depends(get_current_user_id)):
    await _assert_thread_owned(thread_id, user_id)
    state = await thread_store.get(thread_id)
    if not state:
        raise HTTPException(404, "thread not found")
    return state


@router.post("/{thread_id}/state")
async def update_thread_state(thread_id: str, body: StateUpdate, user_id: str = Depends(get_current_user_id)):
    await _assert_thread_owned(thread_id, user_id)
    store_decision(thread_id, body.values)
    return {"ok": True}


@router.get("/{thread_id}/messages")
async def get_thread_messages(thread_id: str, user_id: str = Depends(get_current_user_id)):
    await _assert_thread_owned(thread_id, user_id)

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
