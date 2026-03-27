from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np

from app.core.paths import artifacts_backtests_dir
from app.engine.calibration import CalibratorBundle, apply_calibration, fit_calibrators
from app.engine.features import _sorted_issues_chrono, build_features_for_draws
from app.engine.position_model import PositionModelBundle, _raw_for_vector, train_bundle
from app.engine.reproducibility import build_rng
from app.services.predict_pipeline import default_model_config


class BacktestInsufficientHistoryError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _true_ball_calibrated_prob(
    bundle: PositionModelBundle,
    cal: CalibratorBundle,
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
    zone: str,
    pos_idx: int,
    true_n: int,
) -> float:
    x = np.array(feats_by_zone[zone][true_n]["feature_vector"], dtype=np.float64)
    model = (
        bundle.front_models[pos_idx]
        if zone == "front" and pos_idx < len(bundle.front_models)
        else bundle.back_models[pos_idx]
        if zone == "back" and pos_idx < len(bundle.back_models)
        else None
    )
    r = _raw_for_vector(bundle, model, x)
    cal_m = cal.front[pos_idx] if zone == "front" else cal.back[pos_idx]
    if cal_m is not None:
        return float(cal_m.predict_proba(np.array([[r]], dtype=np.float64))[0, 1])
    return max(1e-6, min(1.0, 1.0 / (35.0 if zone == "front" else 12.0)))


def _score_single_issue(
    hist: list[dict[str, Any]],
    target: dict[str, Any],
    model_version: str,
    model_config: dict[str, Any],
    rng: np.random.Generator,
    ablate_feature_groups: list[str] | None = None,
) -> tuple[float, float, float]:
    """Returns (mean_log_prob_true, mean_ece_proxy, elapsed_seconds)."""
    if len(hist) < 35:
        raise BacktestInsufficientHistoryError(f"history too short: {len(hist)}")
    split = max(int(len(hist) * 0.75), min(30, len(hist) - 8))
    if split >= len(hist) - 3:
        split = max(len(hist) - 8, 20)
    train_draws = hist[:split]
    val_draws = hist[split:]
    if len(val_draws) < 2:
        raise BacktestInsufficientHistoryError("validation slice too small")
    t0 = time.perf_counter()
    bundle = train_bundle(train_draws, model_version, rng, min_hist=30, model_config=model_config)
    cal = fit_calibrators(bundle, train_draws, val_draws, model_version, min_hist=30)
    feats, _, _ = build_features_for_draws(
        hist,
        model_version,
        persist=False,
        ablate_groups=ablate_feature_groups,
    )
    kf = int(model_config.get("search", {}).get("k_front", 12))
    kb = int(model_config.get("search", {}).get("k_back", 6))
    from app.engine.position_model import score_positions

    raw_pos = score_positions(bundle, feats, top_n_front=kf, top_n_back=kb)
    calibrated = apply_calibration(cal, bundle, raw_pos)
    front_sorted = sorted(target["front"])
    back_sorted = sorted(target["back"])
    log_probs: list[float] = []
    ece_rows: list[float] = []
    for pos in range(5):
        p = _true_ball_calibrated_prob(bundle, cal, feats, "front", pos, front_sorted[pos])
        log_probs.append(float(np.log(max(p, 1e-9))))
        ece_rows.append(abs(p - 1.0))
    for pos in range(2):
        p = _true_ball_calibrated_prob(bundle, cal, feats, "back", pos, back_sorted[pos])
        log_probs.append(float(np.log(max(p, 1e-9))))
        ece_rows.append(abs(p - 1.0))
    elapsed = time.perf_counter() - t0
    mean_log = float(np.mean(log_probs)) if log_probs else 0.0
    cal_err = float(np.mean(ece_rows)) if ece_rows else 1.0
    return mean_log, cal_err, elapsed


def run_walk_forward_backtest(
    issues: list[dict[str, Any]],
    *,
    model_config: dict[str, Any],
    base_model_version: str,
    window_config: dict[str, Any],
    rng_seed: int = 42,
    ablate_feature_groups: list[str] | None = None,
) -> dict[str, Any]:
    """
    Walk-forward rolling backtest. Training uses only data strictly before each eval issue.
    """
    min_history = int(window_config.get("min_history_issues", 100))
    n_folds = max(5, int(window_config.get("n_folds", 5)))
    fold_step = max(1, int(window_config.get("fold_step", 1)))
    eval_span = max(1, int(window_config.get("eval_span", 1)))

    chrono = _sorted_issues_chrono(issues)
    for row in chrono:
        row["front"] = sorted(row.get("front") or [])
        row["back"] = sorted(row.get("back") or [])
    n = len(chrono)
    last_eval_start = min_history + (n_folds - 1) * fold_step
    if n <= last_eval_start + eval_span:
        raise BacktestInsufficientHistoryError(
            f"need > {last_eval_start + eval_span} issues, got {n} (min_history={min_history}, n_folds={n_folds})"
        )

    fold_rows: list[dict[str, Any]] = []
    fold_means: list[float] = []
    timings: list[float] = []

    for f in range(n_folds):
        eval_start = min_history + f * fold_step
        fold_scores: list[float] = []
        fold_cal: list[float] = []
        for j in range(eval_span):
            idx = eval_start + j
            if idx >= n:
                break
            hist = chrono[:idx]
            target = chrono[idx]
            rng = build_rng(f"bt_{base_model_version}", str(rng_seed), f"{f}_{j}")
            mean_log, cal_err, elapsed = _score_single_issue(
                hist,
                target,
                base_model_version,
                model_config,
                rng,
                ablate_feature_groups=ablate_feature_groups,
            )
            fold_scores.append(mean_log)
            fold_cal.append(cal_err)
            timings.append(elapsed)
        if not fold_scores:
            continue
        fm = float(np.mean(fold_scores))
        fold_means.append(fm)
        fold_rows.append(
            {
                "fold_index": f,
                "eval_start_issue": str(chrono[eval_start].get("issue", "")),
                "mean_log_prob_true": fm,
                "mean_calibration_gap": float(np.mean(fold_cal)),
            }
        )

    if len(fold_means) < 5:
        raise BacktestInsufficientHistoryError(f"insufficient valid folds: {len(fold_means)}")

    weighted_return = float(np.mean([(m + 8.0) / 8.0 for m in fold_means]))
    weighted_return = max(0.0, min(1.2, weighted_return))
    calibration_error = float(np.mean([r["mean_calibration_gap"] for r in fold_rows]))
    stab = float(np.std(fold_means)) if len(fold_means) > 1 else 0.0
    stability_score = max(0.0, 1.0 - min(1.0, stab))
    fold_min_score = min(fold_means)
    drift_mean = float(np.mean(np.abs(np.diff(fold_means)))) if len(fold_means) > 1 else 0.0

    timings_sorted = sorted(timings)
    p95_idx = max(0, int(round(0.95 * (len(timings_sorted) - 1))))
    predict_p95_seconds = float(timings_sorted[p95_idx]) if timings_sorted else 0.0

    repro_ok = True
    try:
        rng_a = build_rng("bt_rep_a", base_model_version, str(rng_seed))
        rng_b = build_rng("bt_rep_b", base_model_version, str(rng_seed))
        es = min_history
        if es + 1 < n:
            h1, t1 = chrono[:es], chrono[es]
            s1, _, _ = _score_single_issue(h1, t1, base_model_version, model_config, rng_a)
            s2, _, _ = _score_single_issue(h1, t1, base_model_version, model_config, rng_b)
            repro_ok = abs(s1 - s2) < 1e-5
    except Exception:
        repro_ok = False

    diversity_score = stability_score * 0.85 + 0.15 * (1.0 - calibration_error)
    drift_penalty = min(0.5, drift_mean)
    objective_components = {
        "weighted_return": round(weighted_return, 6),
        "calibration_error": round(calibration_error, 6),
        "stability_score": round(stability_score, 6),
        "diversity_score": round(diversity_score, 6),
        "drift_penalty": round(drift_penalty, 6),
        "illegal_rate": 0.0,
        "reproducibility_ok": repro_ok,
        "predict_p95_seconds": round(predict_p95_seconds, 6),
    }

    report_id = f"bt_{base_model_version}_{uuid.uuid4().hex[:12]}"
    report = {
        "report_id": report_id,
        "model_version": base_model_version,
        "target_window": f"{fold_rows[0]['eval_start_issue']}..{fold_rows[-1]['eval_start_issue']}",
        "weighted_return": weighted_return,
        "calibration_error": calibration_error,
        "stability_score": stability_score,
        "created_at": _utc_now().isoformat(),
        "folds": fold_rows,
        "drift_mean": drift_mean,
        "fold_min_score": fold_min_score,
        "reproducibility_passed": repro_ok,
        "predict_p95_seconds": predict_p95_seconds,
        "objective_components": objective_components,
    }
    return report


def report_to_objective_probe_dict(report: dict[str, Any]) -> dict[str, Any]:
    oc = report.get("objective_components") or {}
    backtest_score = float(oc.get("weighted_return", 0.0))
    stability_score = float(oc.get("stability_score", 0.0))
    calibration_score = max(0.0, 1.0 - float(oc.get("calibration_error", 1.0)))
    diversity_score = float(oc.get("diversity_score", 0.0))
    return {
        "illegal_rate": float(oc.get("illegal_rate", 0.0)),
        "reproducible_ok": bool(oc.get("reproducibility_ok", True)),
        "p95_seconds": float(oc.get("predict_p95_seconds", 0.0)),
        "backtest_score": backtest_score,
        "stability_score": stability_score,
        "calibration_score": calibration_score,
        "diversity_score": diversity_score,
    }


def persist_backtest_report(report: dict[str, Any]) -> str:
    h = uuid.uuid4().hex[:8]
    path = artifacts_backtests_dir() / f"backtest_{report.get('model_version', 'mv')}_{h}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return str(path)


def build_real_objective_probe(
    issues: list[dict[str, Any]],
    *,
    base_model_version: str,
    window_config: dict[str, Any] | None = None,
    rng_seed: int = 42,
    patch_merger: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    wc = window_config or {
        "min_history_issues": 80,
        "n_folds": 5,
        "fold_step": 2,
        "eval_span": 1,
    }

    def _probe(params: dict[str, Any]) -> dict[str, Any]:
        cfg = patch_merger(params)
        rep = run_walk_forward_backtest(
            issues,
            model_config=cfg,
            base_model_version=base_model_version,
            window_config=wc,
            rng_seed=rng_seed,
        )
        return report_to_objective_probe_dict(rep)

    return _probe


def run_feature_ablation_suite(
    issues: list[dict[str, Any]],
    *,
    model_version: str,
    window_config: dict[str, Any],
) -> list[dict[str, Any]]:
    from app.engine.features import FEATURE_ABLATION_GROUPS

    base_cfg = default_model_config()
    rows: list[dict[str, Any]] = []
    for group, _keys in FEATURE_ABLATION_GROUPS.items():
        try:
            rep = run_walk_forward_backtest(
                issues,
                model_config=base_cfg,
                base_model_version=model_version,
                window_config=window_config,
                ablate_feature_groups=[group],
            )
            rows.append(
                {
                    "feature_group": group,
                    "enabled": False,
                    "objective_score": float(rep["objective_components"].get("weighted_return", 0.0)),
                    "weighted_return": rep["weighted_return"],
                    "calibration_error": rep["calibration_error"],
                    "stability_score": rep["stability_score"],
                    "notes": "ablated",
                }
            )
        except BacktestInsufficientHistoryError as e:
            rows.append(
                {
                    "feature_group": group,
                    "enabled": False,
                    "objective_score": 0.0,
                    "weighted_return": 0.0,
                    "calibration_error": 1.0,
                    "stability_score": 0.0,
                    "notes": str(e),
                }
            )
    path = artifacts_backtests_dir() / f"feature_ablation_{model_version}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump({"items": rows, "model_version": model_version}, f, ensure_ascii=False, indent=2)
    return rows


def export_drift_threshold_calibration(
    *,
    drift_scores: list[float],
    postmortem_scores: list[float],
    prize_hits: list[float],
    date_tag: str,
) -> dict[str, Any]:
    """Bucket drift scores vs outcomes; write artifact (does not change live thresholds)."""
    if not drift_scores:
        return {
            "sample_size": 0,
            "buckets": [],
            "suggested_thresholds": {"THRESH_NORMAL": 0.35, "THRESH_WARN": 0.55},
            "conclusion": "empty_input",
        }
    n = min(len(drift_scores), len(postmortem_scores), len(prize_hits))
    pairs = list(zip(drift_scores[:n], postmortem_scores[:n], prize_hits[:n], strict=False))
    edges = [0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.01]
    buckets: list[dict[str, Any]] = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=False):
        cell = [(d, p, h) for d, p, h in pairs if lo <= d < hi]
        if not cell:
            continue
        buckets.append(
            {
                "drift_range": [round(lo, 3), round(hi, 3)],
                "count": len(cell),
                "mean_postmortem": float(np.mean([x[1] for x in cell])),
                "mean_prize_proxy": float(np.mean([x[2] for x in cell])),
            }
        )
    out = {
        "sample_size": n,
        "drift_score_buckets": buckets,
        "bucket_avg_postmortem": {f"{b['drift_range']}": b["mean_postmortem"] for b in buckets},
        "bucket_prize_performance": {f"{b['drift_range']}": b["mean_prize_proxy"] for b in buckets},
        "suggested_thresholds": {"THRESH_NORMAL": 0.35, "THRESH_WARN": 0.55},
        "conclusion_summary": "M7 calibration artifact; adjust defaults only after human review.",
    }
    path = artifacts_backtests_dir() / f"drift_threshold_calibration_{date_tag}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out
