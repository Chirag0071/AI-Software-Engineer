from langgraph.graph import (
    StateGraph,
    START,
    END,
)

from backend.graph.state import AgentState

from backend.agents.repository import (
    repository_analyst,
)

from backend.agents.repository_intelligence import (
    repository_intelligence,
)

from backend.agents.planner import (
    planner_agent,
)

from backend.agents.coder import (
    coder_agent,
)

from backend.agents.test_agent import (
    test_agent,
)


def build_workflow():

    graph = StateGraph(
        AgentState
    )

    graph.add_node(
        "repository_analyst",
        repository_analyst,
    )

    graph.add_node(
        "repository_intelligence",
        repository_intelligence,
    )

    graph.add_node(
        "planner",
        planner_agent,
    )

    graph.add_node(
        "coder",
        coder_agent,
    )

    graph.add_node(
        "test_agent",
        test_agent,
    )

    graph.add_edge(
        START,
        "repository_analyst",
    )

    graph.add_edge(
        "repository_analyst",
        "repository_intelligence",
    )

    graph.add_edge(
        "repository_intelligence",
        "planner",
    )

    graph.add_edge(
        "planner",
        "coder",
    )

    graph.add_edge(
        "coder",
        "test_agent",
    )

    graph.add_edge(
        "test_agent",
        END,
    )

    return graph.compile()