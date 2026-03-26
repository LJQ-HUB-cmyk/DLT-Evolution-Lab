from __future__ import annotations

import numpy as np

from app.engine.features import build_features_for_draws, load_issues_dataframe


def _mini_history(n: int) -> list[dict]:
    rng = np.random.default_rng(123)
    items = []
    for i in range(n):
        front = sorted(rng.choice(np.arange(1, 36), size=5, replace=False).tolist())
        back = sorted(rng.choice(np.arange(1, 13), size=2, replace=False).tolist())
        items.append({"issue": f"{25000 + i}", "front": front, "back": back})
    return items


def test_feature_vector_dim_and_keys():
    hist = _mini_history(80)
    by_zone, summary, h = build_features_for_draws(hist, "test-mv", persist=False)
    assert h
    assert summary["n_hist"] == 80
    for n in range(1, 36):
        d = by_zone["front"][n]
        assert "freq_10" in d and "tail_bucket" in d
        assert len(d["feature_vector"]) == summary["feature_dim"]
    for n in range(1, 13):
        d = by_zone["back"][n]
        assert len(d["zone_bucket"]) == 3


def test_load_issues_respects_target_and_window():
    hist = _mini_history(200)
    w = load_issues_dataframe(hist, "25050", 100)
    assert all(int(x["issue"]) < 25050 for x in w)
    assert len(w) <= 100


def test_issue_sort_uses_numeric_order_when_possible():
    hist = [
        {"issue": "99", "front": [1, 2, 3, 4, 5], "back": [1, 2]},
        {"issue": "100", "front": [6, 7, 8, 9, 10], "back": [3, 4]},
    ]
    w = load_issues_dataframe(hist, None, 0)
    assert [row["issue"] for row in w] == ["99", "100"]


def test_feature_samples_fifteen_numbers():
    hist = _mini_history(90)
    by_zone, _, _ = build_features_for_draws(hist, "mv", persist=False)
    checks = [1, 7, 12, 18, 25, 35]
    for n in checks:
        d = by_zone["front"][n]
        assert 0.0 <= d["freq_10"] <= 1.0
        assert d["miss_current"] >= 0.0
