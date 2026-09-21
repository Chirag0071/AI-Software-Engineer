from backend.agents.planner_models import (
    ImplementationPlan,
    PlanTask,
)


def test_plan_task_schema():
    """
    Verify that a PlanTask accepts the expected
    implementation-plan structure.
    """

    task = PlanTask(
        id=1,
        title="Add authentication",
        description="Implement JWT authentication.",
        files_to_modify=[
            "backend/main.py"
        ],
        files_to_create=[
            "backend/auth/dependencies.py"
        ],
        dependencies=[],
        tests_required=[
            "tests/test_auth.py"
        ],
        security_considerations=[
            "Protect the JWT secret."
        ],
    )

    assert task.id == 1
    assert task.title == "Add authentication"
    assert (
        "backend/main.py"
        in task.files_to_modify
    )


def test_implementation_plan_schema():
    """
    Verify that the complete implementation plan
    can be created successfully.
    """

    plan = ImplementationPlan(
        summary="Add JWT authentication.",
        tasks=[
            PlanTask(
                id=1,
                title="Create JWT module",
                description="Create JWT utilities.",
                files_to_create=[
                    "backend/auth/jwt.py"
                ],
                dependencies=[],
            )
        ],
        testing_strategy=[
            "Run pytest."
        ],
        security_strategy=[
            "Keep JWT secret in environment variables."
        ],
    )

    assert plan.summary == "Add JWT authentication."
    assert len(plan.tasks) == 1
    assert plan.tasks[0].id == 1


def test_plan_task_normalizes_string_lists():
    """
    Verify that the Pydantic validators convert
    single strings into lists.
    """

    task = PlanTask(
        id=1,
        title="Test",
        description="Test task",
        files_to_modify="backend/main.py",
        dependencies="1",
    )

    assert task.files_to_modify == [
        "backend/main.py"
    ]

    assert task.dependencies == [
        "1"
    ]