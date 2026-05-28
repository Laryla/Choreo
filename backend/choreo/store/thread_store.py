from choreo.models.thread import Thread, ThreadState
import time

_status: dict[str, str] = {}
_created_at: dict[str, int] = {}


class ThreadStore:
    def save(self, thread: Thread) -> ThreadState:
        _status[thread.thread_id] = "idle"
        _created_at[thread.thread_id] = int(time.time())
        return ThreadState(thread_id=thread.thread_id)

    def get(self, thread_id: str) -> ThreadState | None:
        if thread_id not in _status:
            return None
        return ThreadState(thread_id=thread_id, status=_status[thread_id])

    def set_status(self, thread_id: str, status: str) -> None:
        _status[thread_id] = status

    def list_all(self) -> list[ThreadState]:
        return [
            ThreadState(thread_id=tid, status=st)
            for tid, st in sorted(
                _status.items(),
                key=lambda x: _created_at.get(x[0], 0),
                reverse=True,
            )
        ]


thread_store = ThreadStore()
