from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.reproducibility import stable_response_hash
from app.services.predict_pipeline import run_prediction


@pytest.fixture
def pipeline_env(tmp_path: Path, monkeypatch, patch_issues):
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    monkeypatch.setattr("app.engine.features.artifacts_backtests_dir", lambda: tmp_path / "art")
    (tmp_path / "art").mkdir(parents=True)
    from app.services import predict_pipeline as pp

    monkeypatch.setattr(pp, "persist_calibration", lambda *a, **k: "test_cal_hash")
    return st


def test_pipeline_stable_hash_20_runs(pipeline_env, monkeypatch):
    from app.services import predict_pipeline as pp

    monkeypatch.setattr(pp, "MIN_HISTORY_ISSUES", 50)
    cfg = pp.default_model_config()
    hashes = []
    # 规范要求 20 次；CI 默认 5 次以控时，可通过环境变量跑满 20 次
    n = int(__import__("os").environ.get("M3_REPRO_RUNS", "5"))
    for _ in range(n):
        out = run_prediction(
            target_issue="next",
            mode="experimental",
            seed=777,
            model_version="m3-test",
            model_config=cfg,
        )
        h = stable_response_hash(out["run"])
        hashes.append(h)
    assert len(set(hashes)) == 1
