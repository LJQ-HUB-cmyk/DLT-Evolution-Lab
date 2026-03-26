from __future__ import annotations

from app.engine.optimize import compute_objective_components, default_objective_probe, suggest_params

import optuna


def test_illegal_rate_penalty():
    t, d = compute_objective_components(
        illegal_rate=0.01,
        reproducible_ok=True,
        p95_seconds=1.0,
        backtest_score=1.0,
        stability_score=1.0,
        calibration_score=1.0,
        diversity_score=1.0,
    )
    assert t <= -500.0
    assert "illegal_tickets" in d["penalties"]


def test_repro_penalty():
    t, _ = compute_objective_components(
        illegal_rate=0.0,
        reproducible_ok=False,
        p95_seconds=1.0,
        backtest_score=1.0,
        stability_score=1.0,
        calibration_score=1.0,
        diversity_score=1.0,
    )
    assert t <= -500.0


def test_p95_penalty():
    t, d = compute_objective_components(
        illegal_rate=0.0,
        reproducible_ok=True,
        p95_seconds=10.0,
        backtest_score=1.0,
        stability_score=1.0,
        calibration_score=1.0,
        diversity_score=1.0,
    )
    assert "p95_timeout" in d["penalties"]


def test_suggest_params_bounds():
    study = optuna.create_study(direction="maximize")
    trial = study.ask()
    p = suggest_params(trial)
    assert p["freq_window_main"] in (30, 50, 80, 120)
    assert 40 <= p["beam_width"] <= 180
    assert 0.05 <= p["diversity_lambda"] <= 0.60


def test_default_probe_deterministic_for_same_params():
    p = {"freq_window_main": 50, "ewma_alpha": 0.2}
    p_full = default_objective_probe(p)  # uses hash of full sorted keys internally
    assert "p95_seconds" in p_full
