from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.json_store import JsonStore
from app.services.postmortem_service import build_and_persist_postmortem, build_hit_matrix


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JsonStore:
    st = tmp_path / "storage"
    st.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    s = JsonStore()
    issues = {
        "items": [
            {"issue": "25120", "front": [1, 2, 3, 4, 5], "back": [6, 7]},
        ]
    }
    preds = {
        "official": [],
        "experimental": [
            {
                "run_id": "r1",
                "target_issue": "25120",
                "run_type": "experimental",
                "model_version": "mv",
                "seed": 1,
                "snapshot_hash": "sh",
                "plan1": [{"front": [1, 2, 3, 4, 6], "back": [6, 8], "score": 0.0, "tags": []}],
                "plan2": [],
                "plan3": [{"front": [1, 2, 3, 4, 5], "back": [6, 7], "score": 0.5, "tags": ["stats_aesthetic"]}],
            }
        ],
    }
    s.write("issues.json", issues)
    s.write("predictions.json", preds)
    s.write("postmortems.json", {"items": []})
    return s


def test_hit_matrix_includes_plan3(store: JsonStore) -> None:
    draw = {"issue": "25120", "front": [1, 2, 3, 4, 5], "back": [6, 7]}
    runs = store.read("predictions.json", default={})["experimental"]
    matrix = build_hit_matrix(draw, runs)
    assert matrix and matrix[0].get("tickets")
    plans = {t.get("plan") for t in matrix[0]["tickets"]}
    assert "plan3" in plans


def test_postmortem_persists(store: JsonStore) -> None:
    out = build_and_persist_postmortem(store, "25120", model_version_hint="mv")
    assert "postmortem_id" in out
    pm = store.read("postmortems.json", default={"items": []})
    assert len(pm["items"]) == 1
    preds = store.read("predictions.json", default={})
    exp = preds["experimental"][0]
    assert exp.get("postmortem_status") == "completed"
    assert exp.get("prize_summary", {}).get("postmortem_id") == out["postmortem_id"]
