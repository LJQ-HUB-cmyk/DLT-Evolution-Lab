from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.json_store import JsonStore
from app.services.model_registry_service import evaluate_promotion_after_optimize


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JsonStore:
    st = tmp_path / "storage"
    st.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    s = JsonStore()
    s.write(
        "model_registry.json",
        {
            "items": [
                {
                    "version": "champ",
                    "status": "champion",
                    "credit": 1.0,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "notes": "",
                },
                {
                    "version": "cand",
                    "status": "candidate",
                    "credit": 2.0,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "notes": "",
                },
            ]
        },
    )
    s.write(
        "optimization_runs.json",
        {"items": [{"run_id": "opt1", "status": "succeeded", "gate_passed": True}]},
    )
    return s


def test_promotion_when_gates_pass(store: JsonStore) -> None:
    ev = evaluate_promotion_after_optimize(store, backtest_gate_ok=True, stability_ok=True)
    assert ev.get("promoted") is True
    reg = store.read("model_registry.json", default={"items": []})
    champ = [x for x in reg["items"] if x.get("status") == "champion"]
    assert champ and champ[0].get("version") == "cand"
