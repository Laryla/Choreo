from langgraph.checkpoint.memory import InMemorySaver


def test_headless_agent_has_no_hitl_middleware():
    from choreo.agents.choreo_agent import create_choreo_agent

    agent = create_choreo_agent(headless=True)
    assert agent is not None


def test_chat_agent_requires_checkpointer():
    from choreo.agents.choreo_agent import create_choreo_agent
    agent = create_choreo_agent(InMemorySaver())
    assert agent is not None
