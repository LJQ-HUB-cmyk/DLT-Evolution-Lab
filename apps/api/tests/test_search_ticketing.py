from __future__ import annotations

import numpy as np

from app.engine.calibration import apply_calibration, fit_calibrators
from app.engine.features import build_features_for_draws
from app.engine.position_model import score_positions, train_bundle
from app.engine.reproducibility import build_rng
from app.engine.search import beam_search_tickets, hard_violation_front
from app.engine.ticketing import build_plan1, build_plan2
from app.services.predict_pipeline import default_model_config


def _hist(n: int) -> list[dict]:
    rng = np.random.default_rng(11)
    out = []
    for i in range(n):
        front = sorted(rng.choice(np.arange(1, 36), size=5, replace=False).tolist())
        back = sorted(rng.choice(np.arange(1, 13), size=2, replace=False).tolist())
        out.append({"issue": str(23800 + i), "front": front, "back": back})
    return out


def test_beam_never_emits_illegal_front():
    draws = _hist(130)
    split = int(len(draws) * 0.8)
    train, val = draws[:split], draws[split:]
    rng = build_rng("b" * 64, "mv-s", 0)
    bundle = train_bundle(train, "mv-s", rng, min_hist=30)
    cal = fit_calibrators(bundle, train, val, "mv-s", min_hist=30)
    feats, _, _ = build_features_for_draws(draws, "mv-s", persist=False)
    raw = score_positions(bundle, feats, top_n_front=12, top_n_back=6)
    calibrated = apply_calibration(cal, bundle, raw)
    pool, _ = beam_search_tickets(calibrated, feats, beam_width=24, max_tickets=10)
    for f, b, _ in pool:
        assert not hard_violation_front(sorted(f))
        assert len(set(f)) == 5 and len(set(b)) == 2


def test_plan_counts():
    draws = _hist(130)
    split = int(len(draws) * 0.8)
    train, val = draws[:split], draws[split:]
    rng = build_rng("p" * 64, "mv-p", 0)
    bundle = train_bundle(train, "mv-p", rng, min_hist=30)
    cal = fit_calibrators(bundle, train, val, "mv-p", min_hist=30)
    feats, _, _ = build_features_for_draws(draws, "mv-p", persist=False)
    raw = score_positions(bundle, feats, top_n_front=12, top_n_back=6)
    calibrated = apply_calibration(cal, bundle, raw)
    cfg = default_model_config()
    p1, m1 = build_plan1(calibrated, feats, None, None, cfg)
    rng2 = build_rng("p" * 64, "mv-p", 99)
    p2, m2 = build_plan2(calibrated, feats, cfg, rng2)
    assert len(p1) == 5
    assert len(p2) == 5
    assert "beam_width" in m1
