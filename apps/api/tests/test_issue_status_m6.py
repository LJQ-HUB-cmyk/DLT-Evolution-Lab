from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_issues_status_includes_m6_dashboard_fields() -> None:
    client = TestClient(app)
    resp = client.get("/api/issues/status")
    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "issueCount",
        "modelCount",
        "latestSyncAt",
        "latestIssue",
        "logCount",
        "schedulerLogs",
        "postmortems",
        "optimizationRuns",
    ):
        assert key in data
    assert isinstance(data["schedulerLogs"], list)
    assert isinstance(data["postmortems"], list)
    assert isinstance(data["optimizationRuns"], list)
