from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable

import numpy as np
import optuna
from optuna.samplers import TPESampler

from app.engine.reproducibility import canonical_json_bytes

SEARCH_SPACE_KEYS = (
    "freq_window_main",
    "ewma_alpha",
    "hot_threshold",
    "cold_threshold",
    "beam_width",
    "diversity_lambda",
    "structure_penalty",
    "platt_C",
    "plan2_seed_mix",
    "plan2_soft_constraint_scale",
)


def search_space_hash(params: dict[str, Any]) -> str:
    payload = {k: params.get(k) for k in SEARCH_SPACE_KEYS}
    b = canonical_json_bytes(payload)
    return hashlib.sha256(b).hexdigest()[:16]


def canonical_search_space_hash() -> str:
    """Stable hash of the full M4 search space definition (not trial-specific)."""
    desc: dict[str, Any] = {
        "freq_window_main": [30, 50, 80, 120],
        "ewma_alpha": [0.10, 0.35],
        "hot_threshold": [0.5, 1.5],
        "cold_threshold": [-1.5, -0.5],
        "beam_width": [40, 180],
        "diversity_lambda": [0.05, 0.60],
        "structure_penalty": [0.10, 1.20],
        "platt_C_log": [0.1, 8.0],
        "plan2_seed_mix": [0.0, 1.0],
        "plan2_soft_constraint_scale": [0.6, 1.2],
    }
    return hashlib.sha256(canonical_json_bytes(desc)).hexdigest()[:16]


def suggest_params(trial: optuna.Trial) -> dict[str, Any]:
    return {
        "freq_window_main": trial.suggest_categorical("freq_window_main", [30, 50, 80, 120]),
        "ewma_alpha": trial.suggest_float("ewma_alpha", 0.10, 0.35),
        "hot_threshold": trial.suggest_float("hot_threshold", 0.5, 1.5),
        "cold_threshold": trial.suggest_float("cold_threshold", -1.5, -0.5),
        "beam_width": trial.suggest_int("beam_width", 40, 180),
        "diversity_lambda": trial.suggest_float("diversity_lambda", 0.05, 0.60),
        "structure_penalty": trial.suggest_float("structure_penalty", 0.10, 1.20),
        "platt_C": trial.suggest_float("platt_C", 0.1, 8.0, log=True),
        "plan2_seed_mix": trial.suggest_float("plan2_seed_mix", 0.0, 1.0),
        "plan2_soft_constraint_scale": trial.suggest_float("plan2_soft_constraint_scale", 0.6, 1.2),
    }


def params_to_model_config_patch(params: dict[str, Any]) -> dict[str, Any]:
    scale = float(params["plan2_soft_constraint_scale"])
    sp = float(params["structure_penalty"])
    base_sw = {
        "odd_even": sp,
        "big_small": sp,
        "zone_balance": sp * 1.1,
        "sum_band": sp * 0.85,
        "span_band": sp * 0.85,
        "hot_cold_mix": sp * 0.75,
    }
    plan2_sw = {k: float(v) * scale * 0.6 for k, v in base_sw.items()}
    return {
        "N_hist": int(params["freq_window_main"]) * 3,
        "search": {
            "beam_width": int(params["beam_width"]),
            "k_front": 12,
            "k_back": 6,
            "diversity_lambda": float(params["diversity_lambda"]),
        },
        "structure": {"plan1": base_sw, "plan2": plan2_sw},
        "calibration": {"platt_C": float(params["platt_C"])},
        "feature_tuning": {
            "ewma_alpha": float(params["ewma_alpha"]),
            "hot_threshold": float(params["hot_threshold"]),
            "cold_threshold": float(params["cold_threshold"]),
        },
        "plan2": {
            "seed_mix": float(params["plan2_seed_mix"]),
        },
    }


def compute_objective_components(
    *,
    illegal_rate: float,
    reproducible_ok: bool,
    p95_seconds: float,
    backtest_score: float,
    stability_score: float,
    calibration_score: float,
    diversity_score: float,
) -> tuple[float, dict[str, Any]]:
    penalties: list[tuple[str, float]] = []
    if illegal_rate > 0:
        penalties.append(("illegal_tickets", -1000.0))
    if not reproducible_ok:
        penalties.append(("reproducibility", -1000.0))
    if p95_seconds > 3.0:
        penalties.append(("p95_timeout", -300.0))
    penalty_total = sum(p for _, p in penalties)
    base = (
        0.45 * backtest_score
        + 0.20 * stability_score
        + 0.20 * calibration_score
        + 0.15 * diversity_score
    )
    total = base + penalty_total
    detail = {
        "base_objective": round(base, 6),
        "penalties": {k: v for k, v in penalties},
        "total": round(total, 6),
    }
    return total, detail


def default_objective_probe(params: dict[str, Any]) -> dict[str, Any]:
    """Deterministic proxy objective for optimization when full pipeline is not wired."""
    seed = int(hash(json.dumps(params, sort_keys=True)) % (2**31))
    rng = np.random.default_rng(seed)
    return {
        "illegal_rate": 0.0,
        "reproducible_ok": True,
        "p95_seconds": float(rng.uniform(0.5, 2.5)),
        "backtest_score": float(rng.uniform(0.35, 0.85)),
        "stability_score": float(1.0 - rng.uniform(0.0, 0.25)),
        "calibration_score": float(rng.uniform(0.4, 0.9)),
        "diversity_score": float(rng.uniform(0.3, 0.95)),
    }


def run_optuna_study(
    *,
    run_id: str,
    n_trials: int,
    time_limit_minutes: float,
    objective_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    seed: int = 42,
) -> tuple[dict[str, Any], float, dict[str, Any]]:
    probe = objective_probe or default_objective_probe
    fast = os.environ.get("OPTUNA_FAST", "").lower() in ("1", "true", "yes")
    trials = min(n_trials, 3) if fast else n_trials
    timeout = 5.0 if fast else max(1.0, time_limit_minutes * 60.0)

    study = optuna.create_study(direction="maximize", study_name=run_id, sampler=TPESampler(seed=seed))

    def _obj(trial: optuna.Trial) -> float:
        params = suggest_params(trial)
        m = probe(params)
        total, detail = compute_objective_components(
            illegal_rate=float(m["illegal_rate"]),
            reproducible_ok=bool(m["reproducible_ok"]),
            p95_seconds=float(m["p95_seconds"]),
            backtest_score=float(m["backtest_score"]),
            stability_score=float(m["stability_score"]),
            calibration_score=float(m["calibration_score"]),
            diversity_score=float(m["diversity_score"]),
        )
        trial.set_user_attr("detail", detail)
        return total

    study.optimize(_obj, n_trials=trials, timeout=timeout, show_progress_bar=False)
    best_trial = study.best_trial
    detail = best_trial.user_attrs.get("detail", {})
    summary = {
        "n_trials": len(study.trials),
        "best_value": float(study.best_value),
        "study_name": run_id,
    }
    return study.best_params, float(study.best_value), {"study_summary": summary, "best_detail": detail}
