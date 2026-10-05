from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from langgraph.graph import END, START, StateGraph

from backend.agents.code_review import code_review_agent
from backend.agents.coder import coder_agent
from backend.agents.debugger import debugger_agent
from backend.agents.human_approval import human_approval_agent
from backend.agents.planner import planner_agent
from backend.agents.repository import repository_analyst
from backend.agents.repository_intelligence import repository_intelligence
from backend.agents.test_agent import run_test_agent
from backend.graph.state import AgentState


DEFAULT_MAX_DEBUG_RETRIES = 3


def add_event(
    state: AgentState,
    agent: str,
    event_type: str,
    message: str,
) -> AgentState:

    events = list(
        state.get("events", [])
    )

    events.append(
        {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "agent": agent,
            "event_type": event_type,
            "message": message,
            "metadata": {},
        }
    )

    return {
        **state,
        "events": events,
    }


def wrap_agent(
    name: str,
    function: Callable[
        [AgentState],
        AgentState,
    ],
):
    def wrapped(
        state: AgentState,
    ) -> AgentState:

        state = add_event(
            state,
            name,
            "started",
            f"{name} started",
        )

        try:
            result = function(state)

            return add_event(
                result,
                name,
                "completed",
                f"{name} completed",
            )

        except Exception as exc:
            state = add_event(
                state,
                name,
                "failed",
                str(exc),
            )

            return {
                **state,
                "current_step": f"{name}_failed",
                "errors": [
                    *state.get("errors", []),
                    f"{name}: {exc}",
                ],
            }

    return wrapped


def route_repository_analysis(
    state: AgentState,
) -> str:

    if (
        state.get("current_step")
        == "repository_analysis_complete"
    ):
        return "repository_intelligence"

    return "end"


def route_repository_intelligence(
    state: AgentState,
) -> str:

    if (
        state.get("current_step")
        == "repository_intelligence_complete"
    ):
        return "planner"

    return "end"


def route_planner(
    state: AgentState,
) -> str:

    if (
        state.get("current_step")
        == "planning_complete"
        and state.get("plan")
    ):
        return "coder"

    return "end"


def route_coder(
    state: AgentState,
) -> str:

    if (
        state.get("current_step")
        == "coding_complete"
    ):
        return "test_agent"

    return "end"


def route_testing(
    state: AgentState,
) -> str:

    if state.get(
        "test_results",
        {},
    ).get(
        "success",
        False,
    ):
        return "code_review"

    retries = state.get(
        "debug_retry_count",
        0,
    )

    max_retries = state.get(
        "max_debug_retries",
        DEFAULT_MAX_DEBUG_RETRIES,
    )

    if retries >= max_retries:
        return "end"

    return "debugger"


def route_debugger(
    state: AgentState,
) -> str:

    debugger_result = state.get(
        "debugger_result",
        {},
    )

    if (
        state.get("current_step")
        == "debugging_complete"
        and debugger_result.get(
            "files_to_fix"
        )
    ):
        return "prepare_debug_retry"

    return "end"


def prepare_debug_retry(
    state: AgentState,
) -> AgentState:

    return {
        **state,
        "debug_retry_count": (
            state.get(
                "debug_retry_count",
                0,
            )
            + 1
        ),
        "iteration_count": (
            state.get(
                "iteration_count",
                0,
            )
            + 1
        ),
        "current_step": "debug_retry",
    }


def route_code_review(
    state: AgentState,
) -> str:

    if (
        state.get(
            "review_results",
            {},
        ).get("overall_status")
        == "approved"
    ):
        return "human_approval"

    return "end"


def build_workflow():

    workflow = StateGraph(
        AgentState
    )

    workflow.add_node(
        "repository_analyst",
        wrap_agent(
            "repository_analyst",
            repository_analyst,
        ),
    )

    workflow.add_node(
        "repository_intelligence",
        wrap_agent(
            "repository_intelligence",
            repository_intelligence,
        ),
    )

    workflow.add_node(
        "planner",
        wrap_agent(
            "planner",
            planner_agent,
        ),
    )

    workflow.add_node(
        "coder",
        wrap_agent(
            "coder",
            coder_agent,
        ),
    )

    workflow.add_node(
        "test_agent",
        wrap_agent(
            "test_agent",
            run_test_agent,
        ),
    )

    workflow.add_node(
        "debugger",
        wrap_agent(
            "debugger",
            debugger_agent,
        ),
    )

    workflow.add_node(
        "prepare_debug_retry",
        prepare_debug_retry,
    )

    workflow.add_node(
        "code_review",
        wrap_agent(
            "code_review",
            code_review_agent,
        ),
    )

    workflow.add_node(
        "human_approval",
        wrap_agent(
            "human_approval",
            human_approval_agent,
        ),
    )

    workflow.add_edge(
        START,
        "repository_analyst",
    )

    workflow.add_conditional_edges(
        "repository_analyst",
        route_repository_analysis,
        {
            "repository_intelligence":
                "repository_intelligence",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "repository_intelligence",
        route_repository_intelligence,
        {
            "planner": "planner",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "planner",
        route_planner,
        {
            "coder": "coder",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "coder",
        route_coder,
        {
            "test_agent": "test_agent",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "test_agent",
        route_testing,
        {
            "code_review": "code_review",
            "debugger": "debugger",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "debugger",
        route_debugger,
        {
            "prepare_debug_retry":
                "prepare_debug_retry",
            "end": END,
        },
    )

    workflow.add_edge(
        "prepare_debug_retry",
        "coder",
    )

    workflow.add_conditional_edges(
        "code_review",
        route_code_review,
        {
            "human_approval":
                "human_approval",
            "end": END,
        },
    )

    workflow.add_edge(
        "human_approval",
        END,
    )

    return workflow.compile()


workflow = build_workflow()