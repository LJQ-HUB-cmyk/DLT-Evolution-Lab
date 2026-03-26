from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression

from app.core.paths import artifacts_backtests_dir
from app.engine.features import build_features_for_draws
from app.engine.position_model import PositionModelBundle, _raw_for_vector
from app.engine.reproducibility import canonical_json_bytes, sha256_hex


def _brier(probs: np.ndarray, labels: np.ndarray) -> float:
    return float(np.mean((probs - labels) ** 2))


def _ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(probs)
    if n == 0:
        return 0.0
    for i in range(n_bins):
        m = (probs >= bins[i]) & (probs < bins[i + 1])
        if i == n_bins - 1:
            m = (probs >= bins[i]) & (probs <= bins[i + 1])
        cnt = m.sum()
        if cnt == 0:
            continue
        conf = float(probs[m].mean())
        acc = float(labels[m].mean())
        ece += (cnt / n) * abs(conf - acc)
    return float(ece)


@dataclass
class CalibratorBundle:
    front: list[LogisticRegression | None]
    back: list[LogisticRegression | None]
    metrics: dict[str, Any]


def _collect_val_rows(
    bundle: PositionModelBundle,
    val_draws: list[dict[str, Any]],
    train_prefix: list[dict[str, Any]],
    model_version: str,
    min_hist: int,
) -> tuple[list[list[np.ndarray]], list[list[float]], list[list[np.ndarray]], list[list[float]]]:
    """For each val index, history = train_prefix + val_draws[:i], next = val_draws[i]."""
    rf = [[] for _ in range(5)]
    yf = [[] for _ in range(5)]
    rb = [[] for _ in range(2)]
    yb = [[] for _ in range(2)]

    for i, nxt in enumerate(val_draws):
        hist = train_prefix + val_draws[:i]
        if len(hist) < min_hist:
            continue
        feats, _, _ = build_features_for_draws(hist, model_version, persist=False)
        fs = sorted(nxt["front"])
        bs = sorted(nxt["back"])
        for pos in range(5):
            true_ball = fs[pos]
            for n in range(1, 36):
                x = np.array(feats["front"][n]["feature_vector"], dtype=np.float64)
                model = bundle.front_models[pos] if not bundle.use_fallback else None
                r = _raw_for_vector(bundle, model, x)
                rf[pos].append(np.array([r], dtype=np.float64))
                yf[pos].append(1.0 if n == true_ball else 0.0)
        for pos in range(2):
            true_ball = bs[pos]
            for n in range(1, 13):
                x = np.array(feats["back"][n]["feature_vector"], dtype=np.float64)
                model = bundle.back_models[pos] if not bundle.use_fallback else None
                r = _raw_for_vector(bundle, model, x)
                rb[pos].append(np.array([r], dtype=np.float64))
                yb[pos].append(1.0 if n == true_ball else 0.0)

    return rf, yf, rb, yb


def fit_calibrators(
    bundle: PositionModelBundle,
    train_draws: list[dict[str, Any]],
    val_draws: list[dict[str, Any]],
    model_version: str,
    min_hist: int = 30,
) -> CalibratorBundle:
    rf, yf, rb, yb = _collect_val_rows(bundle, val_draws, train_draws, model_version, min_hist)
    front_cals: list[LogisticRegression | None] = []
    back_cals: list[LogisticRegression | None] = []
    metrics: dict[str, Any] = {"front": [], "back": []}

    for pos in range(5):
        if len(rf[pos]) < 10:
            front_cals.append(None)
            metrics["front"].append({"brier_score": None, "ece": None})
            continue
        X = np.vstack(rf[pos])
        y = np.array(yf[pos])
        if np.unique(y).size < 2:
            front_cals.append(None)
            metrics["front"].append({"brier_score": None, "ece": None})
            continue
        m = LogisticRegression(solver="lbfgs", max_iter=500)
        m.fit(X, y)
        p = m.predict_proba(X)[:, 1]
        front_cals.append(m)
        metrics["front"].append({"brier_score": _brier(p, y), "ece": _ece(p, y)})

    for pos in range(2):
        if len(rb[pos]) < 10:
            back_cals.append(None)
            metrics["back"].append({"brier_score": None, "ece": None})
            continue
        X = np.vstack(rb[pos])
        y = np.array(yb[pos])
        if np.unique(y).size < 2:
            back_cals.append(None)
            metrics["back"].append({"brier_score": None, "ece": None})
            continue
        m = LogisticRegression(solver="lbfgs", max_iter=500)
        m.fit(X, y)
        p = m.predict_proba(X)[:, 1]
        back_cals.append(m)
        metrics["back"].append({"brier_score": _brier(p, y), "ece": _ece(p, y)})

    return CalibratorBundle(front=front_cals, back=back_cals, metrics=metrics)


def apply_calibration(
    cal: CalibratorBundle,
    bundle: PositionModelBundle,
    position_scores: dict[str, Any],
) -> dict[str, Any]:
    out = {"front": [], "back": []}
    for pos, block in enumerate(position_scores["front"]):
        entries = []
        cal_m = cal.front[pos] if pos < len(cal.front) else None
        for item in block["top_numbers"]:
            r = float(item["raw_score"])
            if cal_m is not None:
                cp = float(cal_m.predict_proba(np.array([[r]], dtype=np.float64))[0, 1])
            else:
                cp = float(item["raw_prob"])
            entries.append({**item, "calibrated_prob": max(0.0, min(1.0, cp))})
        entries.sort(key=lambda x: (-x["calibrated_prob"], x["number"]))
        out["front"].append({"position": block["position"], "top_numbers": entries})

    for pos, block in enumerate(position_scores["back"]):
        entries = []
        cal_m = cal.back[pos] if pos < len(cal.back) else None
        for item in block["top_numbers"]:
            r = float(item["raw_score"])
            if cal_m is not None:
                cp = float(cal_m.predict_proba(np.array([[r]], dtype=np.float64))[0, 1])
            else:
                cp = float(item["raw_prob"])
            entries.append({**item, "calibrated_prob": max(0.0, min(1.0, cp))})
        entries.sort(key=lambda x: (-x["calibrated_prob"], x["number"]))
        out["back"].append({"position": block["position"], "top_numbers": entries})

    return out


def persist_calibration(
    cal: CalibratorBundle,
    model_version: str,
    snapshot_hash: str,
) -> str:
    payload: dict[str, Any] = {
        "model_version": model_version,
        "snapshot_hash_prefix": snapshot_hash[:8],
        "metrics": cal.metrics,
        "front_intercepts": [],
        "front_coefs": [],
        "back_intercepts": [],
        "back_coefs": [],
    }
    for m in cal.front:
        if m is None:
            payload["front_intercepts"].append(None)
            payload["front_coefs"].append(None)
        else:
            payload["front_intercepts"].append(float(m.intercept_[0]))
            payload["front_coefs"].append(m.coef_.ravel().tolist())
    for m in cal.back:
        if m is None:
            payload["back_intercepts"].append(None)
            payload["back_coefs"].append(None)
        else:
            payload["back_intercepts"].append(float(m.intercept_[0]))
            payload["back_coefs"].append(m.coef_.ravel().tolist())

    h = sha256_hex(canonical_json_bytes(payload))
    path = artifacts_backtests_dir() / f"calibration_{model_version}_{snapshot_hash[:8]}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump({**payload, "calibration_hash": h}, f, ensure_ascii=False, indent=2)
    return h
