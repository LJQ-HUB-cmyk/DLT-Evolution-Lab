from __future__ import annotations

import numpy as np

from app.engine.features import build_features_for_draws
from app.engine.position_model import score_positions, train_bundle
from app.engine.reproducibility import build_rng


def _hist(n: int) -> list[dict]:
    rng = np.random.default_rng(99)
    out = []
    for i in range(n):
        front = sorted(rng.choice(np.arange(1, 36), size=5, replace=False).tolist())
        back = sorted(rng.choice(np.arange(1, 13), size=2, replace=False).tolist())
        out.append({"issue": str(24100 + i), "front": front, "back": back})
    return out


def test_position_bundle_scores_dimensions():
    draws = _hist(120)
    rng = build_rng("s" * 64, "mv-pos", 1)
    bundle = train_bundle(draws, "mv-pos", rng, min_hist=30)
    feats, _, _ = build_features_for_draws(draws, "mv-pos", persist=False)
    out = score_positions(bundle, feats, top_n_front=12, top_n_back=6)
    assert len(out["front"]) == 5
    assert len(out["back"]) == 2
    for block in out["front"]:
        assert len(block["top_numbers"]) == 12
        for t in block["top_numbers"]:
            assert "raw_score" in t and "raw_prob" in t
            assert 1 <= t["number"] <= 35
