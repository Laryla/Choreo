from fastapi import APIRouter, HTTPException
from choreo.models.thread import Thread, ThreadState
from choreo.models.run import StateUpdate
from choreo.store.thread_store import thread_store
from choreo.agents.middlewares import store_decision

router = APIRouter()


@router.get("/", response_model=list[ThreadState])
async def list_threads():
    return thread_store.list_all()


@router.post("/", response_model=Thread, status_code=201)
async def create_thread():
    thread = Thread()
    thread_store.save(thread)
    return thread


@router.get("/{thread_id}/state", response_model=ThreadState)
async def get_thread_state(thread_id: str):
    state = thread_store.get(thread_id)
    if not state:
        raise HTTPException(404, "thread not found")
    return state


@router.post("/{thread_id}/state")
async def update_thread_state(thread_id: str, body: StateUpdate):
    if not thread_store.get(thread_id):
        raise HTTPException(404, "thread not found")
    # body.values 格式：{"decisions": [{"type": "approve"}]} 等
    store_decision(thread_id, body.values)
    return {"ok": True}
