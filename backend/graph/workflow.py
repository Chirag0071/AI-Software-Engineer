from langgraph.graph import StateGraph, START, END

from backend.graph.state import AgentState

from backend.agents.repository import repository_analyst
from backend.agents.repository_intelligence import (
    repository_intelligence,
)
from backend.agents.planner import planner_agent
from backend.agents.coder import coder_agent
from backend.agents.test_agent import run_test_agent
from backend.agents.debugger import debugger_agent


MAX_DEBUG_RETRIES = 3


def route_after_repository_analysis(
    state: AgentState,
) -> str:
    current_step = state.get(
        "current_step",
        "",
    )

    if current_step == "repository_analysis_complete":
        return "continue"

    return "end"


def route_after_repository_intelligence(
    state: AgentState,
) -> str:
    current_step = state.get(
        "current_step",
        "",
    )

    if current_step == "repository_intelligence_complete":
        return "continue"

    return "end"


def route_after_planning(
    state: AgentState,
) -> str:
    current_step = state.get(
        "current_step",
        "",
    )

    plan = state.get(
        "plan",
        [],
    )

    if (
        current_step == "planning_complete"
        and plan
    ):
        return "continue"

    return "end"


def route_after_coding(
    state: AgentState,
) -> str:
    """
    Hard gate.

    The Test Agent runs ONLY when the Coder
    successfully completes its task.
    """

    current_step = state.get(
        "current_step",
        "",
    )

    if current_step == "coding_complete":
        return "test_agent"

    return "end"


def route_after_testing(
    state: AgentState,
) -> str:
    test_results = state.get(
        "test_results",
        {},
    )

    if test_results.get(
        "success",
        False,
    ):
        return "end"

    retry_count = state.get(
        "debug_retry_count",
        0,
    )

    if retry_count >= MAX_DEBUG_RETRIES:
        return "end"

    return "debugger"


def route_after_debugger(
    state: AgentState,
) -> str:
    current_step = state.get(
        "current_step",
        "",
    )

    debugger_result = state.get(
        "debugger_result",
        {},
    )

    files_to_fix = debugger_result.get(
        "files_to_fix",
        [],
    )

    if (
        current_step == "debugging_complete"
        and files_to_fix
    ):
        return "prepare_retry"

    return "end"


def prepare_debug_retry(
    state: AgentState,
) -> AgentState:
    retry_count = state.get(
        "debug_retry_count",
        0,
    )

    return {
        **state,
        "debug_retry_count": retry_count + 1,
        "current_step": "debug_retry",
    }


def build_workflow():
    """
    Build the autonomous software engineering workflow.

    Repository Analyst
            ↓
    Repository Intelligence
            ↓
    Planner
            ↓
          Coder
            ↓
      Coding Success?
        ↙          ↘
      YES          NO
       ↓            ↓
    Test Agent      END
       ↓
    Tests Passed?
      ↙       ↘
    YES        NO
     ↓          ↓
    END      Debugger
                ↓
        Repair Coder
                ↓
          Test Agent
    """

    graph = StateGraph(
        AgentState
    )

    # Nodes
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
        run_test_agent,
    )

    graph.add_node(
        "debugger",
        debugger_agent,
    )

    graph.add_node(
        "prepare_debug_retry",
        prepare_debug_retry,
    )

    # Start
    graph.add_edge(
        START,
        "repository_analyst",
    )

    # Repository Analyst
    graph.add_conditional_edges(
        "repository_analyst",
        route_after_repository_analysis,
        {
            "continue": "repository_intelligence",
            "end": END,
        },
    )

    # Repository Intelligence
    graph.add_conditional_edges(
        "repository_intelligence",
        route_after_repository_intelligence,
        {
            "continue": "planner",
            "end": END,
        },
    )

    # Planner
    graph.add_conditional_edges(
        "planner",
        route_after_planning,
        {
            "continue": "coder",
            "end": END,
        },
    )

    # Coder
    graph.add_conditional_edges(
        "coder",
        route_after_coding,
        {
            "test_agent": "test_agent",
            "end": END,
        },
    )

    # Test Agent
    graph.add_conditional_edges(
        "test_agent",
        route_after_testing,
        {
            "debugger": "debugger",
            "end": END,
        },
    )

    # Debugger
    graph.add_conditional_edges(
        "debugger",
        route_after_debugger,
        {
            "prepare_retry": "prepare_debug_retry",
            "end": END,
        },
    )

    # Retry Coder
    graph.add_edge(
        "prepare_debug_retry",
        "coder",
    )

    return graph.compile()
