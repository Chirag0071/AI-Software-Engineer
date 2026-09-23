"""
LangGraph workflow for the autonomous software engineering system.
"""

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
    run_test_agent,
)

from backend.agents.debugger import (
    debugger_agent,
)

from backend.agents.code_review import (
    code_review_agent,
)


MAX_DEBUG_RETRIES = 3


# ---------------------------------------------------------------------------
# Repository analysis routing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Planning routing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Coding routing
# ---------------------------------------------------------------------------

def route_after_coding(
    state: AgentState,
) -> str:
    """
    The Test Agent runs only when coding succeeds.
    """

    current_step = state.get(
        "current_step",
        "",
    )

    if current_step == "coding_complete":
        return "test_agent"

    return "end"


# ---------------------------------------------------------------------------
# Testing routing
# ---------------------------------------------------------------------------

def route_after_testing(
    state: AgentState,
) -> str:

    test_results = state.get(
        "test_results",
        {},
    )

    # Tests passed → Code Review.
    if test_results.get(
        "success",
        False,
    ):
        return "code_review"

    retry_count = state.get(
        "debug_retry_count",
        0,
    )

    # Maximum number of debugger/repair cycles reached.
    if retry_count >= MAX_DEBUG_RETRIES:
        return "end"

    return "debugger"


# ---------------------------------------------------------------------------
# Debugger routing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Code Review routing
# ---------------------------------------------------------------------------

def route_after_code_review(
    state: AgentState,
) -> str:

    current_step = state.get(
        "current_step",
        "",
    )

    if current_step == "code_review_complete":
        return "end"

    return "end"


# ---------------------------------------------------------------------------
# Workflow construction
# ---------------------------------------------------------------------------

def build_workflow():
    """
    Build the autonomous software engineering workflow.

    Architecture:

        Repository Analyst
                ↓
        Repository Intelligence
                ↓
             Planner
                ↓
              Coder
                ↓
           Test Agent
                ↓
        ┌───────┴────────┐
        │                │
      PASS              FAIL
        │                │
        ↓                ↓
    Code Review       Debugger
        │                ↓
        ↓          Repair Coder
       END               ↓
                   Test Agent
                         ↓
                   PASS / FAIL
    """

    graph = StateGraph(
        AgentState
    )

    # -----------------------------------------------------------------------
    # Nodes
    # -----------------------------------------------------------------------

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

    graph.add_node(
        "code_review",
        code_review_agent,
    )

    # -----------------------------------------------------------------------
    # Start
    # -----------------------------------------------------------------------

    graph.add_edge(
        START,
        "repository_analyst",
    )

    # -----------------------------------------------------------------------
    # Repository Analyst
    # -----------------------------------------------------------------------

    graph.add_conditional_edges(
        "repository_analyst",
        route_after_repository_analysis,
        {
            "continue": "repository_intelligence",
            "end": END,
        },
    )

    # -----------------------------------------------------------------------
    # Repository Intelligence
    # -----------------------------------------------------------------------

    graph.add_conditional_edges(
        "repository_intelligence",
        route_after_repository_intelligence,
        {
            "continue": "planner",
            "end": END,
        },
    )

    # -----------------------------------------------------------------------
    # Planner
    # -----------------------------------------------------------------------

    graph.add_conditional_edges(
        "planner",
        route_after_planning,
        {
            "continue": "coder",
            "end": END,
        },
    )

    # -----------------------------------------------------------------------
    # Coder
    # -----------------------------------------------------------------------

    graph.add_conditional_edges(
        "coder",
        route_after_coding,
        {
            "test_agent": "test_agent",
            "end": END,
        },
    )

    # -----------------------------------------------------------------------
    # Test Agent
    # -----------------------------------------------------------------------

    graph.add_conditional_edges(
        "test_agent",
        route_after_testing,
        {
            "code_review": "code_review",
            "debugger": "debugger",
            "end": END,
        },
    )

    # -----------------------------------------------------------------------
    # Debugger
    # -----------------------------------------------------------------------

    graph.add_conditional_edges(
        "debugger",
        route_after_debugger,
        {
            "prepare_retry": "prepare_debug_retry",
            "end": END,
        },
    )

    # -----------------------------------------------------------------------
    # Repair Coder
    # -----------------------------------------------------------------------

    graph.add_edge(
        "prepare_debug_retry",
        "coder",
    )

    # -----------------------------------------------------------------------
    # Code Review
    # -----------------------------------------------------------------------

    graph.add_conditional_edges(
        "code_review",
        route_after_code_review,
        {
            "end": END,
        },
    )

    return graph.compile()
