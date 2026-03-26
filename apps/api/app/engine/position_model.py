from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression

from app.engine.features import build_features_for_draws


def _flat_feature_names() -> list[str]:
    from app.engine.features import FEATURE_NAMES_NUMERIC, TAIL_DIM, ZONE_DIM

    names = list(FEATURE_NAMES_NUMERIC)
    names.extend(f"tail_{i}" for i in range(TAIL_DIM))
    names.extend(f"zone_{i}" for i in range(ZONE_DIM))
    return names


@dataclass
class PositionScoreSlice:
    raw_scores: dict[int, float]
    raw_probs: dict[int, float]
    top_n: list[dict[str, Any]]


@dataclass
class PositionModelBundle:
    front_models: list[LogisticRegression | None]
    back_models: list[LogisticRegression | None]
    fallback_weights: np.ndarray
    feature_dim: int
    use_fallback: bool


def _sample_negatives(zone: str, positive: int, rng: np.random.Generator, k: int = 6) -> list[int]:
    pool = list(range(1, 36) if zone == "front" else range(1, 13))
    pool = [x for x in pool if x != positive]
    rng.shuffle(pool)
    return pool[:k]


def _build_training_matrices(
    draws: list[dict[str, Any]],
    model_version: str,
    min_hist: int,
    rng: np.random.Generator,
) -> tuple[list[list[np.ndarray]], list[list[int]], list[list[np.ndarray]], list[list[int]], int]:
    """Returns X_front, y_front, X_back, y_back per position lists, feature_dim."""
    Xf = [[] for _ in range(5)]
    yf = [[] for _ in range(5)]
    Xb = [[] for _ in range(2)]
    yb = [[] for _ in range(2)]
    dim = 0

    for t in range(min_hist, len(draws)):
        hist = draws[:t]
        nxt = draws[t]
        feats_by_zone, _, _ = build_features_for_draws(hist, model_version, persist=False)
        front_sorted = sorted(nxt["front"])
        back_sorted = sorted(nxt["back"])
        for pos in range(5):
            pos_ball = front_sorted[pos]
            xs_pos = np.array(feats_by_zone["front"][pos_ball]["feature_vector"], dtype=np.float64)
            dim = xs_pos.size
            Xf[pos].append(xs_pos)
            yf[pos].append(1)
            for neg in _sample_negatives("front", pos_ball, rng):
                Xf[pos].append(np.array(feats_by_zone["front"][neg]["feature_vector"], dtype=np.float64))
                yf[pos].append(0)
        for pos in range(2):
            pos_ball = back_sorted[pos]
            xs_pos = np.array(feats_by_zone["back"][pos_ball]["feature_vector"], dtype=np.float64)
            Xb[pos].append(xs_pos)
            yb[pos].append(1)
            for neg in _sample_negatives("back", pos_ball, rng, k=4):
                Xb[pos].append(np.array(feats_by_zone["back"][neg]["feature_vector"], dtype=np.float64))
                yb[pos].append(0)

    return Xf, yf, Xb, yb, dim


def train_bundle(
    draws: list[dict[str, Any]],
    model_version: str,
    rng: np.random.Generator,
    min_hist: int = 30,
) -> PositionModelBundle:
    Xf, yf, Xb, yb, dim = _build_training_matrices(draws, model_version, min_hist, rng)
    front_models: list[LogisticRegression | None] = []
    back_models: list[LogisticRegression | None] = []
    use_fallback = False

    for pos in range(5):
        if len(Xf[pos]) < 20:
            use_fallback = True
            break
        X = np.vstack(Xf[pos])
        y = np.array(yf[pos])
        m = LogisticRegression(solver="lbfgs", C=1.0, max_iter=1000)
        m.fit(X, y)
        front_models.append(m)
    if use_fallback:
        w = np.ones(dim) / max(1, dim)
        return PositionModelBundle(
            front_models=[None] * 5,
            back_models=[None] * 2,
            fallback_weights=w,
            feature_dim=dim,
            use_fallback=True,
        )

    for pos in range(2):
        if len(Xb[pos]) < 12:
            use_fallback = True
            break
        X = np.vstack(Xb[pos])
        y = np.array(yb[pos])
        m = LogisticRegression(solver="lbfgs", C=1.0, max_iter=1000)
        m.fit(X, y)
        back_models.append(m)

    if len(back_models) != 2:
        w = np.ones(dim) / max(1, dim)
        return PositionModelBundle(
            front_models=[None] * 5,
            back_models=[None] * 2,
            fallback_weights=w,
            feature_dim=dim,
            use_fallback=True,
        )

    return PositionModelBundle(
        front_models=front_models,
        back_models=back_models,
        fallback_weights=np.ones(dim) / max(1, dim),
        feature_dim=dim,
        use_fallback=False,
    )


def _raw_for_vector(bundle: PositionModelBundle, model: LogisticRegression | None, x: np.ndarray) -> float:
    if bundle.use_fallback or model is None:
        return float(np.dot(bundle.fallback_weights, x))
    return float(model.decision_function(x.reshape(1, -1))[0])


def _softmax(scores: dict[int, float]) -> dict[int, float]:
    items = list(scores.items())
    arr = np.array([s for _, s in items], dtype=np.float64)
    arr = arr - np.max(arr)
    ex = np.exp(arr)
    sm = ex / (ex.sum() + 1e-12)
    return {items[i][0]: float(sm[i]) for i in range(len(items))}


def _top_factors(model: LogisticRegression | None, x: np.ndarray, names: list[str], k: int = 3) -> list[dict[str, float]]:
    if model is None:
        return []
    coef = model.coef_.ravel()
    contrib = coef * x
    idx = np.argsort(-np.abs(contrib))[:k]
    return [{names[i]: float(contrib[i])} for i in idx if i < len(names)]


def score_positions(
    bundle: PositionModelBundle,
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
    top_n_front: int = 12,
    top_n_back: int = 6,
) -> dict[str, Any]:
    names = _flat_feature_names()
    out: dict[str, Any] = {"front": [], "back": []}

    for pos in range(5):
        model = bundle.front_models[pos] if pos < len(bundle.front_models) else None
        raw: dict[int, float] = {}
        for n in range(1, 36):
            x = np.array(feats_by_zone["front"][n]["feature_vector"], dtype=np.float64)
            raw[n] = _raw_for_vector(bundle, model, x)
        probs = _softmax(raw)
        ranked = sorted(raw.items(), key=lambda kv: (-kv[1], kv[0]))
        top = ranked[:top_n_front]
        top_entries = []
        for num, rscore in top:
            x = np.array(feats_by_zone["front"][num]["feature_vector"], dtype=np.float64)
            top_entries.append(
                {
                    "number": num,
                    "raw_score": float(rscore),
                    "raw_prob": float(probs[num]),
                    "top_factors": _top_factors(model, x, names),
                }
            )
        out["front"].append({"position": pos + 1, "top_numbers": top_entries})

    for pos in range(2):
        model = bundle.back_models[pos] if pos < len(bundle.back_models) else None
        raw = {}
        for n in range(1, 13):
            x = np.array(feats_by_zone["back"][n]["feature_vector"], dtype=np.float64)
            raw[n] = _raw_for_vector(bundle, model, x)
        probs = _softmax(raw)
        ranked = sorted(raw.items(), key=lambda kv: (-kv[1], kv[0]))
        top = ranked[:top_n_back]
        top_entries = []
        for num, rscore in top:
            x = np.array(feats_by_zone["back"][num]["feature_vector"], dtype=np.float64)
            top_entries.append(
                {
                    "number": num,
                    "raw_score": float(rscore),
                    "raw_prob": float(probs[num]),
                    "top_factors": _top_factors(model, x, names),
                }
            )
        out["back"].append({"position": pos + 1, "top_numbers": top_entries})

    return out
