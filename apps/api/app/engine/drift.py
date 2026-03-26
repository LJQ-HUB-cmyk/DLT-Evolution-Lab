from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
from scipy.spatial.distance import jensenshannon

from app.models.schemas import DriftReport, DriftLevel

N_REF_DEFAULT = 20
SCORE_TOP_K = 10
EPS = 1e-9
ROUND_DIGITS = 6

# Weights for aggregated drift_score (M4 §5.3)
W_POSITION = 0.30
W_SET = 0.20
W_STRUCTURE = 0.20
W_SCORE_GAP = 0.20
W_OVERLAP = 0.10

THRESH_NORMAL = 0.35
THRESH_WARN = 0.55


def _r6(x: float) -> float:
    return round(float(x), ROUND_DIGITS)


def _softmax_over_top(
    top_numbers: list[dict[str, Any]],
    support_size: int,
) -> np.ndarray:
    """Build a full support distribution: declared probs on listed balls, remainder uniform."""
    v = np.full(support_size, EPS, dtype=np.float64)
    for t in top_numbers:
        n = int(t["number"])
        if 1 <= n <= support_size:
            v[n - 1] = max(float(t.get("calibrated_prob", 0.0)), EPS)
    s = v.sum()
    if s <= 0:
        v[:] = 1.0 / support_size
    else:
        v = v / s
    return v


def _position_distributions_from_summary(position_summary: dict[str, Any]) -> list[np.ndarray]:
    cal = position_summary.get("calibrated") or {}
    out: list[np.ndarray] = []
    for pos in range(5):
        block = (cal.get("front") or [None] * 5)[pos] or {}
        tops = block.get("top_numbers") or []
        out.append(_softmax_over_top(tops, 35))
    for pos in range(2):
        block = (cal.get("back") or [None] * 2)[pos] or {}
        tops = block.get("top_numbers") or []
        out.append(_softmax_over_top(tops, 12))
    return out


def position_dist_drift(
    baseline_summary: dict[str, Any] | None,
    current_summary: dict[str, Any],
) -> float:
    if not baseline_summary:
        return 0.0
    pb = _position_distributions_from_summary(baseline_summary)
    pc = _position_distributions_from_summary(current_summary)
    jsds = []
    for a, b in zip(pb, pc, strict=True):
        j = float(jensenshannon(a, b, base=2.0))
        jsds.append(min(1.0, max(0.0, j)))
    return _r6(float(np.mean(jsds)) if jsds else 0.0)


def _ticket_sets(plan: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
    fs: set[int] = set()
    bs: set[int] = set()
    for t in plan:
        for x in t.get("front") or []:
            fs.add(int(x))
        for x in t.get("back") or []:
            bs.add(int(x))
    return fs, bs


def _jaccard_distance(a: set[int], b: set[int]) -> float:
    if not a and not b:
        return 0.0
    u = len(a | b)
    if u == 0:
        return 0.0
    inter = len(a & b)
    return 1.0 - inter / float(u)


def number_set_drift(
    baseline: dict[str, Any] | None,
    current: dict[str, Any],
) -> float:
    if not baseline:
        return 0.0
    parts = []
    for key in ("plan1", "plan2"):
        b1, b2 = _ticket_sets(baseline.get(key) or [])
        c1, c2 = _ticket_sets(current.get(key) or [])
        parts.append(_jaccard_distance(b1, c1))
        parts.append(_jaccard_distance(b2, c2))
    return _r6(float(np.mean(parts)) if parts else 0.0)


def _zone_counts(front: list[int]) -> tuple[float, float, float]:
    z = [0, 0, 0]
    for x in front:
        if 1 <= x <= 12:
            z[0] += 1
        elif 13 <= x <= 24:
            z[1] += 1
        else:
            z[2] += 1
    return tuple(v / 5.0 for v in z)


def _consecutive_segments(sorted_front: list[int]) -> int:
    if len(sorted_front) < 2:
        return 0
    seg = 0
    i = 0
    while i < len(sorted_front) - 1:
        if sorted_front[i + 1] == sorted_front[i] + 1:
            seg += 1
            j = i + 1
            while j < len(sorted_front) - 1 and sorted_front[j + 1] == sorted_front[j] + 1:
                j += 1
            i = j
        i += 1
    return seg


def _structure_vector_for_plan(plan: list[dict[str, Any]], feats_by_num: dict[str, Any] | None) -> np.ndarray:
    """Aggregate structure vector over tickets in a plan (mean)."""
    if not plan:
        return np.zeros(7, dtype=np.float64)
    vecs = []
    for t in plan:
        f = sorted(int(x) for x in t.get("front") or [])
        b = sorted(int(x) for x in t.get("back") or [])
        if len(f) != 5 or len(b) != 2:
            continue
        odd = sum(1 for x in f if x % 2 == 1) / 5.0
        big = sum(1 for x in f if x >= 18) / 5.0
        z0, z1, z2 = _zone_counts(f)
        s = sum(f) / 165.0
        span = (max(f) - min(f)) / 34.0
        cons = _consecutive_segments(f) / 4.0
        hot = 0.5
        if feats_by_num:
            tags = []
            for n in f:
                key = str(n)
                if key in feats_by_num:
                    tags.append(float(feats_by_num[key].get("hot_cold_tag", 0.0)))
            if tags:
                hot = float(np.mean(tags))
        vecs.append(np.array([odd, big, z0, z1, z2, s, span, cons, hot], dtype=np.float64))
    if not vecs:
        return np.zeros(9, dtype=np.float64)
    return np.mean(np.stack(vecs, axis=0), axis=0)


def _structure_vector(run: dict[str, Any]) -> np.ndarray:
    fs = (run.get("feature_summary") or {}).get("by_number_front") or {}
    v1 = _structure_vector_for_plan(run.get("plan1") or [], fs if isinstance(fs, dict) else None)
    v2 = _structure_vector_for_plan(run.get("plan2") or [], fs if isinstance(fs, dict) else None)
    return (v1 + v2) / 2.0 if v1.shape == v2.shape else v1


def structure_drift(baseline: dict[str, Any] | None, current: dict[str, Any]) -> float:
    if not baseline:
        return 0.0
    a = _structure_vector(baseline)
    b = _structure_vector(current)
    ranges = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.5], dtype=np.float64)
    k = len(a)
    manhattan = float(np.sum(np.abs(a - b)[:k] / (ranges[:k] + EPS)) / max(k, 1))
    return _r6(min(1.0, manhattan))


def _top_scores(run: dict[str, Any], k: int) -> tuple[float, float]:
    scores: list[float] = []
    for key in ("plan1", "plan2"):
        for t in run.get(key) or []:
            scores.append(float(t.get("score", 0.0)))
    scores.sort(reverse=True)
    top = scores[:k]
    if not top:
        return 0.0, 0.0
    mu = float(np.mean(top))
    var = float(np.var(top))
    return mu, var


def score_gap_drift(
    baseline: dict[str, Any] | None,
    current: dict[str, Any],
    history_runs: list[dict[str, Any]],
) -> float:
    c_mu, c_var = _top_scores(current, SCORE_TOP_K)
    if not baseline:
        hist_mu: list[float] = []
        hist_var: list[float] = []
        for r in history_runs:
            m, v = _top_scores(r, SCORE_TOP_K)
            hist_mu.append(m)
            hist_var.append(v)
        if not hist_mu:
            return 0.0
        ref_mu = float(np.mean(hist_mu))
        ref_std = float(np.std(hist_mu)) + EPS
        z = abs(c_mu - ref_mu) / ref_std
        return _r6(min(1.0, z / 4.0))
    b_mu, b_var = _top_scores(baseline, SCORE_TOP_K)
    d_mu = abs(c_mu - b_mu)
    d_var = abs(c_var - b_var)
    hist_dmu: list[float] = []
    hist_dvar: list[float] = []
    for r in history_runs:
        m, v = _top_scores(r, SCORE_TOP_K)
        hist_dmu.append(abs(m - b_mu))
        hist_dvar.append(abs(v - b_var))
    std_mu = float(np.std(hist_dmu)) if hist_dmu else 0.0
    std_var = float(np.std(hist_dvar)) if hist_dvar else 0.0
    z_mu = d_mu / max(std_mu, EPS)
    z_var = d_var / max(std_var, EPS)
    z = (z_mu + z_var) / 2.0
    return _r6(min(1.0, z / 4.0))


def _exact_ticket_overlap(plan_a: list[dict[str, Any]], plan_b: list[dict[str, Any]]) -> float:
    def _key(t: dict[str, Any]) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return (tuple(sorted(int(x) for x in t.get("front") or [])), tuple(sorted(int(x) for x in t.get("back") or [])))

    sa = {_key(t) for t in plan_a}
    sb = {_key(t) for t in plan_b}
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / float(max(len(sa | sb), 1))


def plan_overlap_drift(
    baseline: dict[str, Any] | None,
    current: dict[str, Any],
    history_runs: list[dict[str, Any]],
) -> float:
    if not baseline:
        return 0.0
    o_cur = (
        _exact_ticket_overlap(baseline.get("plan1") or [], current.get("plan1") or [])
        + _exact_ticket_overlap(baseline.get("plan2") or [], current.get("plan2") or [])
    ) / 2.0
    overlaps: list[float] = []
    for r in history_runs:
        o = (
            _exact_ticket_overlap(baseline.get("plan1") or [], r.get("plan1") or [])
            + _exact_ticket_overlap(baseline.get("plan2") or [], r.get("plan2") or [])
        ) / 2.0
        overlaps.append(o)
    ref_mean = float(np.mean(overlaps)) if overlaps else o_cur
    ref_std = float(np.std(overlaps)) if overlaps else 0.0
    delta = abs(o_cur - ref_mean) / max(ref_std, EPS)
    mapped = 1.0 / (1.0 + math.exp(-delta))
    return _r6(min(1.0, max(0.0, mapped)))


def aggregate_drift_score(
    position: float,
    nset: float,
    structure: float,
    score_gap: float,
    overlap: float,
) -> float:
    s = (
        W_POSITION * position
        + W_SET * nset
        + W_STRUCTURE * structure
        + W_SCORE_GAP * score_gap
        + W_OVERLAP * overlap
    )
    return _r6(min(1.0, max(0.0, s)))


def classify_drift_level(
    drift_score: float,
    subs: tuple[float, float, float, float, float],
) -> DriftLevel:
    if sum(1 for x in subs if x >= 0.75) >= 2:
        return "CRITICAL"
    if drift_score >= THRESH_WARN:
        return "CRITICAL"
    if drift_score >= THRESH_NORMAL:
        return "WARN"
    if any(x >= 0.80 for x in subs):
        return "WARN"
    return "NORMAL"


def build_trigger_actions(level: DriftLevel) -> list[str]:
    if level == "NORMAL":
        return []
    actions = ["feature_decay", "credit_update"]
    if level == "WARN":
        actions.extend(["structure_penalty_delta", "model_watch"])
    else:
        actions.extend(["structure_penalty_delta", "beam_shrink", "mark_unstable", "enqueue_optimize"])
    return actions


def compute_drift_report(
    *,
    run_id: str,
    target_issue: str,
    model_version: str,
    snapshot_hash: str,
    baseline: dict[str, Any] | None,
    current: dict[str, Any],
    history_runs: list[dict[str, Any]] | None = None,
    created_at: datetime | None = None,
) -> DriftReport:
    hist = history_runs or []
    pos = position_dist_drift(
        baseline.get("position_summary") if baseline else None,
        current.get("position_summary") or {},
    )
    nset = number_set_drift(baseline, current)
    struct = structure_drift(baseline, current)
    sg = score_gap_drift(baseline, current, hist)
    ov = plan_overlap_drift(baseline, current, hist)
    subs = (pos, nset, struct, sg, ov)
    dscore = aggregate_drift_score(pos, nset, struct, sg, ov)
    level = classify_drift_level(dscore, subs)
    actions = build_trigger_actions(level)
    return DriftReport(
        run_id=run_id,
        target_issue=target_issue,
        model_version=model_version,
        snapshot_hash=snapshot_hash,
        position_dist_drift=pos,
        number_set_drift=nset,
        structure_drift=struct,
        score_gap_drift=sg,
        plan_overlap_drift=ov,
        drift_score=dscore,
        drift_level=level,
        trigger_actions=actions,
        created_at=created_at or datetime.now(timezone.utc),
    )
