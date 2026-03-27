from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.backtest import BacktestInsufficientHistoryError, run_walk_forward_backtest
from app.services.predict_pipeline import default_model_config


def _synthetic_issues(n: int) -> list[dict]:
    out: list[dict] = []
    for i in range(n):
        issue = f"{25000 + i:05d}"
        f = sorted(
            [
                (i % 35) + 1,
                ((i + 3) % 35) + 1,
                ((i + 7) % 35) + 1,
                ((i + 11) % 35) + 1,
                ((i + 19) % 35) + 1,
            ]
        )
        b = sorted([(i % 12) + 1, ((i + 5) % 12) + 1])
        out.append({"issue": issue, "front": f, "back": b})
    return out


def test_walk_forward_requires_enough_issues():
    issues = _synthetic_issues(20)
    with pytest.raises(BacktestInsufficientHistoryError):
        run_walk_forward_backtest(
            issues,
            model_config=default_model_config(),
            base_model_version="t-mv",
            window_config={"min_history_issues": 100, "n_folds": 5, "fold_step": 1, "eval_span": 1},
        )


def test_walk_forward_no_future_leak_and_folds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.engine.backtest.artifacts_backtests_dir", lambda: tmp_path)
    issues = _synthetic_issues(130)
    wc = {"min_history_issues": 55, "n_folds": 5, "fold_step": 3, "eval_span": 1}
    rep = run_walk_forward_backtest(
        issues,
        model_config=default_model_config(),
        base_model_version="t-mv",
        window_config=wc,
        rng_seed=7,
    )
    assert len(rep["folds"]) >= 5
    assert "report_id" in rep
    assert "objective_components" in rep
    assert "weighted_return" in rep
    assert rep["fold_min_score"] <= max(f["mean_log_prob_true"] for f in rep["folds"])


def test_report_fields_complete():
    issues = _synthetic_issues(130)
    rep = run_walk_forward_backtest(
        issues,
        model_config=default_model_config(),
        base_model_version="t-mv",
        window_config={"min_history_issues": 55, "n_folds": 5, "fold_step": 3, "eval_span": 1},
    )
    for k in (
        "folds",
        "drift_mean",
        "fold_min_score",
        "reproducibility_passed",
        "predict_p95_seconds",
        "objective_components",
    ):
        assert k in rep
