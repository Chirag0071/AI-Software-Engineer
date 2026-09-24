from backend.agents.human_approval import (
    human_approval_agent,
)


def test_human_approval_waits_for_approved_review():
    state = {
        "review_results": {
            "overall_status": "approved",
            "summary": "Code review passed.",
            "issues": [],
            "strengths": [
                "Tests pass.",
                "Implementation is consistent.",
            ],
            "security_concerns": [],
        },
    }

    result = human_approval_agent(state)

    assert result["approval_required"] is True
    assert result["approval_result"]["approved"] is False
    assert result["current_step"] == (
        "waiting_for_human_approval"
    )


def test_human_approval_blocks_failed_review():
    state = {
        "review_results": {
            "overall_status": "changes_requested",
            "summary": "Changes are required.",
            "issues": [
                {
                    "severity": "high",
                    "category": "security",
                    "file": "backend/main.py",
                    "description": "Security issue.",
                    "recommendation": "Fix the issue.",
                }
            ],
            "strengths": [],
            "security_concerns": [
                "Security issue detected."
            ],
        },
    }

    result = human_approval_agent(state)

    assert result["approval_required"] is False
    assert result["approval_result"]["approved"] is False
    assert result["current_step"] == "approval_blocked"