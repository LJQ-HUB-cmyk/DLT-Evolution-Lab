from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.json_store import JsonStore


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    st = tmp_path / "storage"
    st.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    import app.routers.api as api_mod

    api_mod.store = JsonStore()
    s = api_mod.store
    s.write(
        "model_registry.json",
        {
            "items": [
                {
                    "version": "m5-api",
                    "status": "champion",
                    "credit": 1.0,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "notes": "",
                }
            ]
        },
    )
    s.write(
        "issues.json",
        {"items": [{"issue": "25140", "front": [1, 2, 3, 4, 5], "back": [6, 7]}]},
    )
    s.write("predictions.json", {"official": [], "experimental": []})
    s.write("postmortems.json", {"items": []})
    s.write("optimization_runs.json", {"items": []})
    s.write("scheduler_logs.json", {"logs": [], "idempotency": {}, "alert_state": {}})
    return TestClient(app)


def test_sync_has_scheduler_context(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.automation_pipeline.sync_official_sources",
        lambda: {
            "ok": True,
            "degraded": False,
            "mode": "test",
            "syncedAt": "t",
            "issueCount": 0,
            "newIssueCount": 0,
            "ruleVersionCount": 0,
            "warnings": [],
            "snapshots": {"draw": {"sha256": "abc"}},
        },
    )
    r = api_client.post("/api/sync")
    assert r.status_code == 200
    body = r.json()
    assert "scheduler_context" in body
    assert body["scheduler_context"].get("trigger_source") == "manual"
    assert "task_status" in body["scheduler_context"]


def test_postmortem_contract(api_client: TestClient) -> None:
    r = api_client.post("/api/postmortem/25140")
    assert r.status_code == 200
    j = r.json()
    assert "postmortem_id" in j
    assert "score_summary" in j
    assert "triggered_actions" in j


def test_runs_enriched(api_client: TestClient) -> None:
    import app.routers.api as api_mod

    p = api_mod.store.read("predictions.json", default={})
    p.setdefault("experimental", []).append(
        {
            "run_id": "rx",
            "target_issue": "25140",
            "prize_summary": {"postmortem_id": "pmx", "best_prize_level": "no_prize"},
        }
    )
    api_mod.store.write("predictions.json", p)
    r = api_client.get("/api/runs")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[-1].get("postmortem_ref") == "pmx"
