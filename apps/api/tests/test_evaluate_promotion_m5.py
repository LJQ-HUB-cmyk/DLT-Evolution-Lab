from __future__ import annotations

import pytest

from app.services.json_store import JsonStore
from app.services.model_registry_service import evaluate_promotion_after_optimize


def _minimal_store(tmp_path, monkeypatch):
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    return JsonStore()


def test_evaluate_promotion_no_runs(tmp_path, monkeypatch):
    store = _minimal_store(tmp_path, monkeypatch)
    store.write("model_registry.json", {"items": []})
    store.write("optimization_runs.json", {"items": []})
    ev = evaluate_promotion_after_optimize(store)
    assert ev["promoted"] is False
    assert "no_succeeded_optimize" in ev["reason"] or "no_candidate" in ev["reason"]


def test_evaluate_promotion_gates_false(tmp_path, monkeypatch):
    store = _minimal_store(tmp_path, monkeypatch)
    store.write(
        "model_registry.json",
        {
            "items": [
                {
                    "version": "ch",
                    "status": "champion",
                    "credit_score": 80.0,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
                {
                    "version": "ca",
                    "status": "candidate",
                    "credit_score": 90.0,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            ]
        },
    )
    store.write(
        "optimization_runs.json",
        {"items": [{"status": "completed", "run_id": "o1"}]},
    )
    ev = evaluate_promotion_after_optimize(store, backtest_gate_ok=False, stability_ok=True)
    assert ev["promoted"] is False
    assert ev["reason"] == "gates_failed"
