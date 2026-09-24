"""
Human Approval Agent.

This agent does not modify the repository.

It prepares the final state after Code Review and marks the
workflow as waiting for human approval.
"""

from backend.graph.state import AgentState


def human_approval_agent(
    state: AgentState,
) -> AgentState:
    """
    Pause the workflow and request human approval.

    The actual approval decision is intentionally not made by
    the AI agent. A human must approve the generated changes
    before the workflow can continue to GitHub PR creation.
    """

    review_results = state.get(
        "review_results",
        {},
    )

    review_status = review_results.get(
        "overall_status"
    )

    if review_status != "approved":
        return {
            **state,
            "approval_required": False,
            "approval_result": {
                "approved": False,
                "reviewer": "",
                "comment": (
                    "Human approval is unavailable because "
                    "the code review requested changes."
                ),
            },
            "current_step": "approval_blocked",
        }

    return {
        **state,
        "approval_required": True,
        "approval_result": {
            "approved": False,
            "reviewer": "",
            "comment": (
                "Waiting for human approval before "
                "GitHub PR creation."
            ),
        },
        "current_step": "waiting_for_human_approval",
    }