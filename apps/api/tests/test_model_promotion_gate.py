from __future__ import annotations

import pytest

from app.services.json_store import JsonStore
from app.services.model_registry_service import (
    evaluate_walk_forward_gate,
    try_promote_candidate,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    st = tmp_path / "storage"
    st.mkdir()
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    return JsonStore()


def test_gate_degraded_never_passes():
    g = evaluate_walk_forward_gate(
        champion_objective=1.0,
        candidate_objective=10.0,
        champion_fold_min=0.5,
        candidate_fold_min=0.5,
        drift_champion_mean=0.0,
        drift_candidate_mean=0.0,
        reproducibility_passes=20,
        reproducibility_total=20,
        predict_p95=1.0,
        degraded_test_data=True,
    )
    assert g["passed"] is False


def test_gate_passes_when_all_ok():
    g = evaluate_walk_forward_gate(
        champion_objective=1.0,
        candidate_objective=1.05,
        champion_fold_min=0.5,
        candidate_fold_min=0.49,
        drift_champion_mean=0.2,
        drift_candidate_mean=0.22,
        reproducibility_passes=20,
        reproducibility_total=20,
        predict_p95=1.0,
        degraded_test_data=False,
    )
    assert g["passed"] is True


def test_try_promote_blocked_when_gate_fails(store):
    reg = {
        "items": [
            {
                "version": "champ",
                "status": "champion",
                "credit_score": 70.0,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "version": "cand1",
                "status": "candidate",
                "credit_score": 80.0,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        ]
    }
    store.write("model_registry.json", reg)
    res = try_promote_candidate(
        store,
        "cand1",
        gate_result={"passed": False, "degraded_test_data": True, "reason": "test"},
    )
    assert res["ok"] is False
    r2 = store.read("model_registry.json", default={"items": []})
    assert any(x.get("version") == "champ" and x.get("status") == "champion" for x in r2["items"])


def test_try_promote_succeeds_when_gate_passes(store):
    reg = {
        "items": [
            {
                "version": "champ",
                "status": "champion",
                "credit_score": 70.0,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "version": "cand1",
                "status": "candidate",
                "credit_score": 80.0,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        ]
    }
    store.write("model_registry.json", reg)
    store.write("scheduler_logs.json", {"logs": []})
    gr = {"passed": True, "degraded_test_data": False, "reason": "unit"}
    res = try_promote_candidate(store, "cand1", gate_result=gr)
    assert res["ok"] is True
    r2 = store.read("model_registry.json", default={"items": []})
    assert any(x.get("version") == "cand1" and x.get("status") == "champion" for x in r2["items"])
