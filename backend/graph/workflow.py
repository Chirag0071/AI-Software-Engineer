from langgraph.graph import StateGraph, START, END

from backend.graph.state import AgentState
from backend.agents.planner import planner_agent
from backend.agents.repository import repository_analyst


def build_workflow():
    graph = StateGraph(AgentState)

    graph.add_node(
        "repository_analyst",
        repository_analyst
    )

    graph.add_node(
        "planner",
        planner_agent
    )

    graph.add_edge(
        START,
        "repository_analyst"
    )

    graph.add_edge(
        "repository_analyst",
        "planner"
    )

    graph.add_edge(
        "planner",
        END
    )

    return graph.compile()