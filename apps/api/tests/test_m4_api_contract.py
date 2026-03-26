from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.json_store import JsonStore


@pytest.fixture
def m4_client(tmp_path: Path, monkeypatch, patch_issues):
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    import app.routers.api as api_mod

    api_mod.store = JsonStore()
    (st / "model_registry.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "version": "m4-api",
                        "status": "champion",
                        "credit_score": 70.0,
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "notes": "",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (st / "predictions.json").write_text(
        json.dumps({"official": [], "experimental": []}), encoding="utf-8"
    )
    (st / "scheduler_logs.json").write_text(json.dumps({"logs": []}), encoding="utf-8")
    (st / "optimization_runs.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    return TestClient(app)


def test_predict_returns_m4_fields(m4_client: TestClient):
    r = m4_client.post("/api/predict/next", params={"seed": 42})
    assert r.status_code == 200
    j = r.json()
    assert "drift_report" in j
    assert "model_credit" in j
    assert "optimize_triggered" in j
    assert j["drift_report"]["drift_score"] >= 0.0


def test_models_returns_credit_fields(m4_client: TestClient):
    r = m4_client.get("/api/models")
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert items
    assert "credit_score" in items[0]
