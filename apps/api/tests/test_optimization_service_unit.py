from __future__ import annotations

import json

import pytest

from app.services.json_store import JsonStore
from app.services.optimization_service import (
    mark_last_optimization_succeeded,
    queue_optimization_run,
    should_trigger_optimize,
)


def _store_with_champion(tmp_path, monkeypatch, **champ_fields):
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    store = JsonStore()
    item = {
        "version": "c1",
        "status": "champion",
        "credit_score": 70.0,
        "consecutive_warn_count": 0,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    item.update(champ_fields)
    store.write("model_registry.json", {"items": [item]})
    store.write("optimization_runs.json", {"items": []})
    store.write("scheduler_logs.json", {"logs": []})
    return store


def test_should_trigger_low_credit(tmp_path, monkeypatch):
    store = _store_with_champion(tmp_path, monkeypatch, credit_score=40.0)
    ok, reasons = should_trigger_optimize(store)
    assert ok is True
    assert "credit_below_55" in reasons


def test_should_trigger_consecutive_warn(tmp_path, monkeypatch):
    store = _store_with_champion(tmp_path, monkeypatch, consecutive_warn_count=3)
    ok, reasons = should_trigger_optimize(store)
    assert ok is True
    assert "consecutive_warn" in reasons


def test_mark_last_optimization_succeeded_updates_last(tmp_path, monkeypatch):
    store = _store_with_champion(tmp_path, monkeypatch)
    store.write(
        "optimization_runs.json",
        {"items": [{"run_id": "x", "status": "completed"}]},
    )
    mark_last_optimization_succeeded(store, gate_passed=True)
    last = store.read("optimization_runs.json", default={"items": []})["items"][-1]
    assert last.get("optimization_succeeded") is True


def test_queue_optimization_runs_fast(tmp_path, monkeypatch):
    import os

    os.environ["OPTUNA_FAST"] = "1"
    store = _store_with_champion(tmp_path, monkeypatch)
    out = queue_optimization_run(store, reason="t", triggered_by="unit")
    assert out.get("run_id")
    assert out.get("status") in ("completed", "failed")
