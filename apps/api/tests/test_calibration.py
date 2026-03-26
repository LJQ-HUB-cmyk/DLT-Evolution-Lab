from __future__ import annotations

import numpy as np

from app.engine.calibration import apply_calibration, fit_calibrators
from app.engine.features import build_features_for_draws
from app.engine.position_model import score_positions, train_bundle
from app.engine.reproducibility import build_rng


def _hist(n: int) -> list[dict]:
    rng = np.random.default_rng(5)
    out = []
    for i in range(n):
        front = sorted(rng.choice(np.arange(1, 36), size=5, replace=False).tolist())
        back = sorted(rng.choice(np.arange(1, 13), size=2, replace=False).tolist())
        out.append({"issue": str(24000 + i), "front": front, "back": back})
    return out


def test_calibrated_probs_in_unit_interval():
    draws = _hist(130)
    split = int(len(draws) * 0.8)
    train, val = draws[:split], draws[split:]
    rng = build_rng("c" * 64, "mv-cal", 0)
    bundle = train_bundle(train, "mv-cal", rng, min_hist=30)
    cal = fit_calibrators(bundle, train, val, "mv-cal", min_hist=30)
    feats, _, _ = build_features_for_draws(draws, "mv-cal", persist=False)
    raw = score_positions(bundle, feats, top_n_front=8, top_n_back=4)
    out = apply_calibration(cal, bundle, raw)
    for zone in ("front", "back"):
        for block in out[zone]:
            for t in block["top_numbers"]:
                p = t["calibrated_prob"]
                assert 0.0 <= p <= 1.0


def test_fit_calibrators_gracefully_handles_single_class(monkeypatch):
    def _fake_collect(*args, **kwargs):
        rf = [[np.array([0.1]), np.array([0.2]), np.array([0.3])] for _ in range(5)]
        yf = [[1.0, 1.0, 1.0] for _ in range(5)]
        rb = [[np.array([0.1]), np.array([0.2]), np.array([0.3])] for _ in range(2)]
        yb = [[0.0, 0.0, 0.0] for _ in range(2)]
        return rf, yf, rb, yb

    monkeypatch.setattr("app.engine.calibration._collect_val_rows", _fake_collect)
    cal = fit_calibrators(
        bundle=None,  # type: ignore[arg-type]
        train_draws=[],
        val_draws=[],
        model_version="mv",
        min_hist=30,
    )
    assert all(x is None for x in cal.front)
    assert all(x is None for x in cal.back)
