from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.automation_pipeline import resolve_next_target_issue, run_draw_poll_job
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
                    "version": "mv-scheduler",
                    "status": "champion",
                    "credit": 1.0,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "notes": "",
                }
            ]
        },
    )
    s.write("predictions.json", {"official": [], "experimental": []})
    s.write("postmortems.json", {"items": []})
    return s


def test_resolve_next_target_issue_from_storage(env_store: JsonStore) -> None:
    env_store.write(
        "issues.json",
        {"items": [{"issue": "25140"}, {"issue": "25139"}, {"issue": "25138"}]},
    )
    assert resolve_next_target_issue(env_store) == "25141"


def test_draw_poll_job_skips_without_open_prediction_issue(
    env_store: JsonStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.automation_pipeline.sync_official_sources",
        lambda: {
            "ok": True,
            "degraded": False,
            "mode": "test",
            "syncedAt": "2026-03-26T00:00:00Z",
            "issueCount": 0,
            "newIssueCount": 0,
            "ruleVersionCount": 1,
            "warnings": [],
            "snapshots": {},
        },
    )
    out = run_draw_poll_job(env_store, trigger_source="manual")
    assert out["status"] == "skipped"
    assert out["reason"] == "no_open_prediction_issue"


def test_draw_poll_job_auto_selects_open_issue_and_chains(
    env_store: JsonStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_store.write(
        "issues.json",
        {
            "items": [
                {
                    "issue": "25150",
                    "draw_date": "2026-03-25",
                    "front": [1, 2, 3, 4, 5],
                    "back": [6, 7],
                }
            ]
        },
    )
    env_store.write(
        "predictions.json",
        {
            "official": [{"target_issue": "25150", "run_id": "off_25150"}],
            "experimental": [],
        },
    )
    monkeypatch.setattr(
        "app.services.automation_pipeline.sync_official_sources",
        lambda: {
            "ok": True,
            "degraded": False,
            "mode": "test",
            "syncedAt": "2026-03-26T00:00:00Z",
            "issueCount": 1,
            "newIssueCount": 0,
            "ruleVersionCount": 1,
            "warnings": [],
            "snapshots": {},
        },
    )
    monkeypatch.setattr(
        "app.services.automation_pipeline.run_draw_poll_and_chain",
        lambda *_args, **kwargs: {
            "ingest": {"status": "succeeded"},
            "postmortem": {"status": "succeeded"},
            "optimize": None,
            "promotion": {"promoted": False},
            "target_issue_echo": kwargs.get("target_issue"),
        },
    )

    out = run_draw_poll_job(env_store, trigger_source="manual")
    assert out["status"] == "succeeded"
    assert out["target_issue"] == "25150"
    assert out["target_issue_echo"] == "25150"
