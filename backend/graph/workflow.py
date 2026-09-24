"""
LangGraph workflow for the Autonomous AI Software Engineer.

Workflow:

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
   ┌────┴────┐
 PASS       FAIL
   ↓          ↓
Code Review  Debugger
   ↓          ↓
Human       Prepare Retry
Approval       ↓
   ↓          Coder
  END
"""

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from backend.agents.code_review import (
    code_review_agent,
)
from backend.agents.coder import (
    coder_agent,
)
from backend.agents.debugger import (
    debugger_agent,
)
from backend.agents.human_approval import (
    human_approval_agent,
)
from backend.agents.planner import (
    planner_agent,
)
from backend.agents.repository import (
    repository_analyst,
)
from backend.agents.repository_intelligence import (
    repository_intelligence,
)
from backend.agents.test_agent import (
    run_test_agent,
)
from backend.graph.state import AgentState


MAX_DEBUG_RETRIES = 3


def route_after_repository_analysis(
    state: AgentState,
) -> str:
    """
    Route repository analysis.
    """

    if (
        state.get("current_step")
        == "repository_analysis_complete"
    ):
        return "repository_intelligence"

    return "end"


def route_after_repository_intelligence(
    state: AgentState,
) -> str:
    """
    Route repository intelligence.
    """

    if (
        state.get("current_step")
        == "repository_intelligence_complete"
    ):
        return "planner"

    return "end"


def route_after_planner(
    state: AgentState,
) -> str:
    """
    Route planning to Coder.
    """

    plan = state.get(
        "plan",
        [],
    )

    if (
        state.get("current_step")
        == "planning_complete"
        and plan
    ):
        return "coder"

    return "end"


def route_after_coder(
    state: AgentState,
) -> str:
    """
    Route Coder output to Test Agent.
    """

    if (
        state.get("current_step")
        == "coding_complete"
    ):
        return "test_agent"

    return "end"


def route_after_testing(
    state: AgentState,
) -> str:
    """
    Decide whether to review, debug, or stop.
    """

    test_results = state.get(
        "test_results",
        {},
    )

    if test_results.get(
        "success",
        False,
    ):
        return "code_review"

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
    """
    Route debugger output back to Coder
    when a repair is required.
    """

    if (
        state.get("current_step")
        == "debugging_complete"
    ):
        debugger_result = state.get(
            "debugger_result",
            {},
        )

        files_to_fix = debugger_result.get(
            "files_to_fix",
            [],
        )

        if files_to_fix:
            return "prepare_debug_retry"

    return "end"


def prepare_debug_retry(
    state: AgentState,
) -> AgentState:
    """
    Prepare state for another Coder → Test cycle.
    """

    retry_count = state.get(
        "debug_retry_count",
        0,
    )

    return {
        **state,
        "debug_retry_count": retry_count + 1,
        "current_step": "debug_retry",
    }


def route_after_code_review(
    state: AgentState,
) -> str:
    """
    Route approved code to the human approval gate.

    Code that requires changes does not proceed to
    human approval.
    """

    review_results = state.get(
        "review_results",
        {},
    )

    if (
        review_results.get(
            "overall_status"
        )
        == "approved"
    ):
        return "human_approval"

    return "end"


def build_workflow():
    """
    Build and compile the complete LangGraph workflow.
    """

    workflow = StateGraph(
        AgentState
    )

    # -------------------------------------------------
    # Nodes
    # -------------------------------------------------

    workflow.add_node(
        "repository_analyst",
        repository_analyst,
    )

    workflow.add_node(
        "repository_intelligence",
        repository_intelligence,
    )

    workflow.add_node(
        "planner",
        planner_agent,
    )

    workflow.add_node(
        "coder",
        coder_agent,
    )

    workflow.add_node(
        "test_agent",
        run_test_agent,
    )

    workflow.add_node(
        "debugger",
        debugger_agent,
    )

    workflow.add_node(
        "prepare_debug_retry",
        prepare_debug_retry,
    )

    workflow.add_node(
        "code_review",
        code_review_agent,
    )

    workflow.add_node(
        "human_approval",
        human_approval_agent,
    )

    # -------------------------------------------------
    # Entry
    # -------------------------------------------------

    workflow.add_edge(
        START,
        "repository_analyst",
    )

    # -------------------------------------------------
    # Repository Analyst
    # -------------------------------------------------

    workflow.add_conditional_edges(
        "repository_analyst",
        route_after_repository_analysis,
        {
            "repository_intelligence":
                "repository_intelligence",
            "end": END,
        },
    )

    # -------------------------------------------------
    # Repository Intelligence
    # -------------------------------------------------

    workflow.add_conditional_edges(
        "repository_intelligence",
        route_after_repository_intelligence,
        {
            "planner": "planner",
            "end": END,
        },
    )

    # -------------------------------------------------
    # Planner
    # -------------------------------------------------

    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "coder": "coder",
            "end": END,
        },
    )

    # -------------------------------------------------
    # Coder
    # -------------------------------------------------

    workflow.add_conditional_edges(
        "coder",
        route_after_coder,
        {
            "test_agent": "test_agent",
            "end": END,
        },
    )

    # -------------------------------------------------
    # Testing
    # -------------------------------------------------

    workflow.add_conditional_edges(
        "test_agent",
        route_after_testing,
        {
            "code_review": "code_review",
            "debugger": "debugger",
            "end": END,
        },
    )

    # -------------------------------------------------
    # Debugger
    # -------------------------------------------------

    workflow.add_conditional_edges(
        "debugger",
        route_after_debugger,
        {
            "prepare_debug_retry":
                "prepare_debug_retry",
            "end": END,
        },
    )

    # -------------------------------------------------
    # Debug retry
    # -------------------------------------------------

    workflow.add_edge(
        "prepare_debug_retry",
        "coder",
    )

    # -------------------------------------------------
    # Code Review
    # -------------------------------------------------

    workflow.add_conditional_edges(
        "code_review",
        route_after_code_review,
        {
            "human_approval": "human_approval",
            "end": END,
        },
    )

    # -------------------------------------------------
    # Human Approval
    # -------------------------------------------------

    workflow.add_edge(
        "human_approval",
        END,
    )

    return workflow.compile()


workflow = build_workflow()