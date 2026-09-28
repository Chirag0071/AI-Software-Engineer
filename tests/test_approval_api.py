from fastapi.testclient import TestClient

from backend.main import (
    RUN_STORE,
    app,
)


client = TestClient(app)


def setup_function():
    RUN_STORE.clear()


def test_get_missing_run():
    response = client.get(
        "/runs/does-not-exist"
    )

    assert response.status_code == 404


def test_approve_missing_run():
    response = client.post(
        "/runs/does-not-exist/approve",
        json={
            "reviewer": "tester",
            "comment": "Approved.",
        },
    )

    assert response.status_code == 404


def test_reject_missing_run():
    response = client.post(
        "/runs/does-not-exist/reject",
        json={
            "reviewer": "tester",
            "comment": "Needs changes.",
        },
    )

    assert response.status_code == 404


def test_approve_run_requires_waiting_state():
    RUN_STORE["test-run"] = {
        "current_step": "testing_complete",
        "approval_required": False,
    }

    response = client.post(
        "/runs/test-run/approve",
        json={
            "reviewer": "tester",
            "comment": "Approved.",
        },
    )

    assert response.status_code == 409


def test_reject_run_requires_waiting_state():
    RUN_STORE["test-run"] = {
        "current_step": "testing_complete",
        "approval_required": False,
    }

    response = client.post(
        "/runs/test-run/reject",
        json={
            "reviewer": "tester",
            "comment": "Rejected.",
        },
    )

    assert response.status_code == 409


def test_get_waiting_run():
    RUN_STORE["test-run"] = {
        "current_step": "waiting_for_human_approval",
        "approval_required": True,
        "approval_result": {
            "approved": False,
            "reviewer": "",
            "comment": "",
        },
        "github_result": {},
        "test_results": {
            "success": True,
        },
        "review_results": {
            "overall_status": "approved",
        },
        "generated_files": [],
        "modified_files": [],
        "errors": [],
    }

    response = client.get(
        "/runs/test-run"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["run_id"] == "test-run"

    assert data["step"] == (
        "waiting_for_human_approval"
    )

    assert data["approval_required"] is True


def test_reject_waiting_run():
    RUN_STORE["test-run"] = {
        "current_step": "waiting_for_human_approval",
        "approval_required": True,
        "approval_result": {
            "approved": False,
            "reviewer": "",
            "comment": "",
        },
        "github_result": {},
        "errors": [],
    }

    response = client.post(
        "/runs/test-run/reject",
        json={
            "reviewer": "tester",
            "comment": "Please improve the implementation.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "rejected"

    assert data["step"] == (
        "human_approval_rejected"
    )

    assert (
        data["approval_result"]["approved"]
        is False
    )

    assert (
        data["approval_result"]["reviewer"]
        == "tester"
    )