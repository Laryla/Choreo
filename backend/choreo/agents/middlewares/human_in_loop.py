# 存储每个 thread 的待 resume 决策（由 threads router 写入，runs router 消费）
_pending_decisions: dict[str, dict] = {}


def store_decision(thread_id: str, decision: dict) -> None:
    _pending_decisions[thread_id] = decision


def pop_decision(thread_id: str) -> dict | None:
    return _pending_decisions.pop(thread_id, None)
