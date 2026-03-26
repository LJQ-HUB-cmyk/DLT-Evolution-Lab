from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.reproducibility import stable_response_hash
from app.services.predict_pipeline import run_prediction


@pytest.fixture
def m4_pipeline_env(tmp_path: Path, monkeypatch, patch_issues):
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    monkeypatch.setattr("app.engine.features.artifacts_backtests_dir", lambda: tmp_path / "art")
    (tmp_path / "art").mkdir(parents=True)
    from app.services import predict_pipeline as pp

    monkeypatch.setattr(pp, "persist_calibration", lambda *a, **k: "test_cal_hash")
    (st / "model_registry.json").write_text(
        '{"items":[{"version":"m4-repro","status":"champion","credit_score":70.0,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}]}',
        encoding="utf-8",
    )
    return st


def test_m4_predict_hash_stable_across_runs(m4_pipeline_env, monkeypatch):
    from app.services import predict_pipeline as pp

    monkeypatch.setattr(pp, "MIN_HISTORY_ISSUES", 50)
    cfg = pp.default_model_config()
    n = int(__import__("os").environ.get("M4_REPRO_RUNS", "5"))
    hashes = []
    for _ in range(n):
        out = run_prediction(
            target_issue="next",
            mode="experimental",
            seed=999,
            model_version="m4-repro",
            model_config=cfg,
        )
        h = stable_response_hash(out["run"])
        hashes.append(h)
    assert len(set(hashes)) == 1
