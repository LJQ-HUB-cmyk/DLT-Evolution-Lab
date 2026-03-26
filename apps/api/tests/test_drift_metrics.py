from __future__ import annotations

from datetime import datetime, timezone

from app.engine.drift import (
    aggregate_drift_score,
    classify_drift_level,
    compute_drift_report,
    number_set_drift,
    plan_overlap_drift,
    position_dist_drift,
    score_gap_drift,
    structure_drift,
)
from app.models.schemas import DriftReport


def _cal_block(top: list[tuple[int, float]], support: int) -> dict:
    return {"top_numbers": [{"number": n, "calibrated_prob": p} for n, p in top]}


def _pos_summary_from_uniform(support: int, k: int) -> dict:
    probs = [1.0 / k] * k
    nums = list(range(1, k + 1))[:k]
    front = []
    for _ in range(5):
        front.append(_cal_block(list(zip(nums, probs)), support))
    back = []
    for _ in range(2):
        back.append(_cal_block(list(zip([1, 2], [0.5, 0.5])), 12))
    return {"calibrated": {"front": front, "back": back}}


def test_position_dist_identical_zero():
    s = _pos_summary_from_uniform(35, 10)
    d = position_dist_drift(s, s)
    assert abs(d - 0.0) <= 1e-6


def test_position_dist_different_positive():
    a = _pos_summary_from_uniform(35, 10)
    b = _pos_summary_from_uniform(35, 10)
    b["calibrated"]["front"][0] = _cal_block([(34, 0.99), (1, 0.01)], 35)
    d = position_dist_drift(a, b)
    assert d > 1e-6


def test_number_set_jaccard():
    base = {
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2]}],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4]}],
    }
    same = {
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2]}],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4]}],
    }
    assert abs(number_set_drift(base, same) - 0.0) <= 1e-6
    diff = {
        "plan1": [{"front": [11, 12, 13, 14, 15], "back": [5, 6]}],
        "plan2": [{"front": [16, 17, 18, 19, 20], "back": [7, 8]}],
    }
    assert number_set_drift(base, diff) > 0.4


def test_structure_drift_bounds():
    a = {
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2], "score": 1.0}],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4], "score": 1.0}],
        "feature_summary": {},
    }
    b = {
        "plan1": [{"front": [30, 31, 32, 33, 34], "back": [11, 12], "score": 1.0}],
        "plan2": [{"front": [25, 26, 27, 28, 29], "back": [10, 11], "score": 1.0}],
        "feature_summary": {},
    }
    d = structure_drift(a, b)
    assert 0.0 <= d <= 1.0 + 1e-6


def test_score_gap_zscore_normalized():
    base = {
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2], "score": 10.0} for _ in range(5)],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4], "score": 9.0} for _ in range(5)],
    }
    cur = {
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2], "score": 50.0} for _ in range(5)],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4], "score": 49.0} for _ in range(5)],
    }
    hist = [
        {
            "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2], "score": float(x)} for _ in range(5)],
            "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4], "score": float(x - 1)} for _ in range(5)],
        }
        for x in range(10, 15)
    ]
    sg = score_gap_drift(base, cur, hist)
    assert 0.0 <= sg <= 1.0 + 1e-6


def test_plan_overlap_sigmoid():
    base = {
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2]} for _ in range(5)],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4]} for _ in range(5)],
    }
    cur = {
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2]} for _ in range(5)],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4]} for _ in range(5)],
    }
    hist = [cur for _ in range(5)]
    o = plan_overlap_drift(base, cur, hist)
    assert abs(o - 0.5) <= 0.5 + 1e-6


def test_aggregate_weights_sum():
    s = aggregate_drift_score(0.1, 0.2, 0.3, 0.4, 0.5)
    exp = 0.30 * 0.1 + 0.20 * 0.2 + 0.20 * 0.3 + 0.20 * 0.4 + 0.10 * 0.5
    assert abs(s - exp) <= 1e-6


def test_classify_hard_critical_two_high():
    subs = (0.1, 0.76, 0.76, 0.1, 0.1)
    assert classify_drift_level(0.1, subs) == "CRITICAL"


def test_compute_drift_report_schema():
    baseline = {
        "position_summary": _pos_summary_from_uniform(35, 8),
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2], "score": 1.0} for _ in range(5)],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4], "score": 1.0} for _ in range(5)],
    }
    current = {
        "position_summary": _pos_summary_from_uniform(35, 8),
        "plan1": [{"front": [11, 12, 13, 14, 15], "back": [6, 7], "score": 2.0} for _ in range(5)],
        "plan2": [{"front": [16, 17, 18, 19, 20], "back": [8, 9], "score": 2.0} for _ in range(5)],
    }
    r = compute_drift_report(
        run_id="r1",
        target_issue="25100",
        model_version="mv",
        snapshot_hash="ab",
        baseline=baseline,
        current=current,
        history_runs=[],
        created_at=datetime.now(timezone.utc),
    )
    DriftReport.model_validate(r.model_dump())
    assert r.drift_level in ("NORMAL", "WARN", "CRITICAL")
