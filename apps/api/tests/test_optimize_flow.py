from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.json_store import JsonStore
from app.services.optimization_service import enqueue_optimize, execute_optimization_run


@pytest.fixture
def opt_client(tmp_path: Path, monkeypatch):
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
                        "version": "m4-test",
                        "status": "champion",
                        "credit": 1.0,
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
    (st / "optimization_runs.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (st / "predictions.json").write_text(
        json.dumps({"official": [], "experimental": []}), encoding="utf-8"
    )
    (st / "scheduler_logs.json").write_text(json.dumps({"logs": []}), encoding="utf-8")
    return TestClient(app), st


def test_optimize_api_returns_run_id(opt_client):
    client, _ = opt_client
    import os

    os.environ["OPTUNA_FAST"] = "1"
    r = client.post("/api/optimize", json={"budget_trials": 3, "time_limit_minutes": 1})
    assert r.status_code == 200
    j = r.json()
    assert j.get("optimization_run_id")
    assert j.get("status") in ("completed", "failed")


def test_enqueue_without_execute_stays_queued(tmp_path, monkeypatch):
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    store = JsonStore()
    (st / "model_registry.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "version": "mv1",
                        "status": "champion",
                        "credit_score": 70.0,
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (st / "optimization_runs.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (st / "scheduler_logs.json").write_text(json.dumps({"logs": []}), encoding="utf-8")
    out = enqueue_optimize(
        store,
        trigger_source="manual",
        base_model_version="mv1",
        budget_trials=2,
        time_limit_minutes=1,
        execute=False,
    )
    assert out.get("status") == "queued"
    last = store.read("optimization_runs.json", default={"items": []})["items"][-1]
    assert last.get("status") == "queued"


def test_enqueue_execute_registers_candidate(tmp_path, monkeypatch):
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    store = JsonStore()
    (st / "model_registry.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "version": "mv1",
                        "status": "champion",
                        "credit_score": 70.0,
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (st / "optimization_runs.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (st / "scheduler_logs.json").write_text(json.dumps({"logs": []}), encoding="utf-8")
    import os

    os.environ["OPTUNA_FAST"] = "1"
    out = enqueue_optimize(
        store,
        trigger_source="manual",
        base_model_version="mv1",
        budget_trials=2,
        time_limit_minutes=1,
        execute=True,
    )
    assert out.get("status") == "completed"
    reg = store.read("model_registry.json", default={"items": []})
    assert any("cand-" in str(x.get("version", "")) for x in reg.get("items", []))


def test_execute_missing_run_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: tmp_path / "s")
    (tmp_path / "s").mkdir()
    store = JsonStore()
    store.write("optimization_runs.json", {"items": []})
    with pytest.raises(KeyError):
        execute_optimization_run(store, "missing")
