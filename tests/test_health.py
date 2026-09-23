from backend.main import health_check


def test_health_check_structure_and_values():
    """
    Verify that the health-check utility returns
    the expected structure and values.
    """

    result = health_check()

    assert isinstance(
        result,
        dict,
    )

    assert result.get(
        "status"
    ) == "healthy"

    assert result.get(
        "workflow"
    ) == "ready"

    expected_keys = {
        "status",
        "workflow",
    }

    assert set(
        result.keys()
    ) == expected_keys
