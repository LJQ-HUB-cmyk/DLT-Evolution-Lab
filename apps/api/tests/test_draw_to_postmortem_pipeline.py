from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.automation_pipeline import run_draw_poll_and_chain
from app.services.json_store import JsonStore


@pytest.fixture
def env_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JsonStore:
    st = tmp_path / "storage"
    nd = tmp_path / "norm"
    st.mkdir(parents=True, exist_ok=True)
    nd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    monkeypatch.setattr("app.core.paths.normalized_data_dir", lambda: nd)
    monkeypatch.setattr("app.services.official_sync_service.storage_dir", lambda: st)
    monkeypatch.setattr("app.services.official_sync_service.normalized_data_dir", lambda: nd)
    (nd / "issues.json").write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
    s = JsonStore()
    s.write(
        "model_registry.json",
        {
            "items": [
                {
                    "version": "mv-pipe",
                    "status": "champion",
                    "credit": 1.0,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "notes": "",
                },
                {
                    "version": "mv-cand",
                    "status": "candidate",
                    "credit": 1.5,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "notes": "",
                },
            ]
        },
    )
    s.write(
        "predictions.json",
        {
            "official": [],
            "experimental": [
                {
                    "run_id": "run_pipe",
                    "target_issue": "25130",
                    "run_type": "experimental",
                    "model_version": "mv-pipe",
                    "seed": 1,
                    "snapshot_hash": "sh",
                    "plan1": [{"front": [1, 2, 3, 4, 5], "back": [6, 7], "score": 0.0, "tags": []}],
                    "plan2": [],
                }
            ],
        },
    )
    # 近 6 期均值 >= 55 且最近一期有奖，避免本集成测试拉起完整 Optuna
    pm_rows = [
        {
            "postmortem_score": 60.0,
            "hit_matrix": [{"tickets": [{"prize_level": 9}]}],
            "prize_distribution": {"9": 1},
        }
        for _ in range(6)
    ]
    s.write("postmortems.json", {"items": pm_rows})
    s.write("optimization_runs.json", {"items": []})
    return s


def test_draw_poll_chain_creates_postmortem(env_store: JsonStore) -> None:
    out = run_draw_poll_and_chain(
        env_store,
        target_issue="25130",
        front=[1, 2, 3, 4, 5],
        back=[6, 7],
        trigger_source="manual",
    )
    assert out["ingest"]["status"] == "succeeded"
    pm = out.get("postmortem") or {}
    assert pm.get("status") == "succeeded"
    items = env_store.read("postmortems.json", default={"items": []})["items"]
    assert any(x.get("issue") == "25130" for x in items)
