from __future__ import annotations

from typing import Any

import numpy as np

from app.core.paths import artifacts_backtests_dir
from app.engine.reproducibility import canonical_json_bytes, sha256_hex

FEATURE_NAMES_NUMERIC = (
    "freq_10",
    "freq_30",
    "freq_50",
    "freq_100",
    "miss_current",
    "ewma_hotness",
    "adjacent_last",
    "repeat_last",
    "sum_contrib_proxy",
    "span_contrib_proxy",
    "hot_cold_tag",
    "last_issue_interference",
)
TAIL_DIM = 10
ZONE_DIM = 3

# M7 特征分组（消融用）：组名 -> raw_feature_dict 中需置零的键
FEATURE_ABLATION_GROUPS: dict[str, tuple[str, ...]] = {
    "freq": ("freq_10", "freq_30", "freq_50", "freq_100"),
    "miss": ("miss_current",),
    "ewma": ("ewma_hotness",),
    "adjacent_repeat": ("adjacent_last", "repeat_last"),
    "tail": (),  # handled via zeroing tail_bucket after raw
    "zone": (),
    "sum_span": ("sum_contrib_proxy", "span_contrib_proxy"),
    "interference": ("last_issue_interference",),
    "hot_cold": ("hot_cold_tag",),
}


def _apply_feature_ablation_raw(d: dict[str, Any], ablate_groups: set[str]) -> dict[str, Any]:
    out = dict(d)
    for g in ablate_groups:
        keys = FEATURE_ABLATION_GROUPS.get(g, ())
        for k in keys:
            if k in out:
                out[k] = 0.0
        if g == "tail":
            out["tail_bucket"] = [0.0] * TAIL_DIM
        if g == "zone":
            out["zone_bucket"] = [0.0] * ZONE_DIM
    return out


def _sorted_issues_chrono(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(item: dict[str, Any]) -> tuple[int, str]:
        issue = str(item.get("issue", ""))
        if issue.isdigit():
            return (0, f"{int(issue):012d}")
        return (1, issue)

    return sorted(issues, key=_key)


def _window_issues(issues_chrono: list[dict[str, Any]], n_hist: int) -> list[dict[str, Any]]:
    if n_hist <= 0:
        return issues_chrono
    return issues_chrono[-n_hist:]


def _freq_in_window(draws: list[dict[str, Any]], number: int, zone: str, w: int) -> float:
    if w <= 0:
        return 0.0
    tail = draws[-w:] if len(draws) >= w else draws
    if not tail:
        return 0.0
    c = 0
    for d in tail:
        nums = d["front"] if zone == "front" else d["back"]
        if number in nums:
            c += 1
    return c / float(len(tail))


def _miss_current(draws: list[dict[str, Any]], number: int, zone: str, cap: int) -> float:
    if not draws:
        return float(cap)
    seen = 0
    for d in reversed(draws):
        nums = d["front"] if zone == "front" else d["back"]
        if number in nums:
            return float(min(seen, cap))
        seen += 1
    return float(min(seen, cap))


def _ewma_hotness(draws: list[dict[str, Any]], number: int, zone: str, alpha: float = 0.2) -> float:
    ewma = 0.0
    for d in draws:
        nums = d["front"] if zone == "front" else d["back"]
        x = 1.0 if number in nums else 0.0
        ewma = alpha * x + (1.0 - alpha) * ewma
    return float(ewma)


def _zone_one_hot(n: int, zone: str) -> np.ndarray:
    v = np.zeros(ZONE_DIM, dtype=np.float64)
    if zone == "front":
        if 1 <= n <= 12:
            v[0] = 1.0
        elif 13 <= n <= 24:
            v[1] = 1.0
        else:
            v[2] = 1.0
    else:
        if 1 <= n <= 4:
            v[0] = 1.0
        elif 5 <= n <= 8:
            v[1] = 1.0
        else:
            v[2] = 1.0
    return v


def _tail_one_hot(n: int) -> np.ndarray:
    v = np.zeros(TAIL_DIM, dtype=np.float64)
    v[n % 10] = 1.0
    return v


def _hot_cold_tag_from_z(z: float) -> float:
    if z > 0.8:
        return 1.0
    if z < -0.8:
        return -1.0
    return 0.0


def _last_issue_interference(last_front: list[int] | None, n: int, zone: str) -> float:
    if zone != "front" or not last_front:
        return 0.0
    cnt = sum(1 for x in last_front if abs(x - n) <= 2)
    return float(min(1.0, cnt / 5.0))


def _sum_span_targets(draws: list[dict[str, Any]]) -> tuple[float, float, float]:
    if not draws:
        return 90.0, 18.0, 0.5
    sums = [sum(d["front"]) for d in draws]
    spans = [max(d["front"]) - min(d["front"]) for d in draws]
    s = float(np.median(sums))
    sp = float(np.median(spans))
    return s, sp, float(np.median([x for d in draws for x in d["front"]]) or 17.0)


def _sum_contrib_proxy(n: int, target_sum: float) -> float:
    ideal = target_sum / 5.0
    scale = 12.0
    raw = 1.0 - abs(n - ideal) / scale
    return float(max(-1.0, min(1.0, raw)))


def _span_contrib_proxy(n: int, target_span: float, median_ball: float) -> float:
    scale = 10.0
    spread = abs(n - median_ball) / scale
    raw = min(1.0, spread / (target_span / 2.0 + 1e-6))
    return float(max(-1.0, min(1.0, raw * 2.0 - 0.5)))


def raw_feature_dict(
    number: int,
    zone: str,
    draws: list[dict[str, Any]],
    freq30_list: list[float],
    last_front: list[int] | None,
    last_back: list[int] | None,
    sum_target: float,
    span_target: float,
    median_ball: float,
) -> dict[str, Any]:
    f10 = _freq_in_window(draws, number, zone, 10)
    f30 = _freq_in_window(draws, number, zone, 30)
    f50 = _freq_in_window(draws, number, zone, 50)
    f100 = _freq_in_window(draws, number, zone, 100)
    miss = _miss_current(draws, number, zone, cap=len(draws) or 100)
    ewma = _ewma_hotness(draws, number, zone)
    last_nums = last_front if zone == "front" else (last_back or [])
    adj = 0.0
    rep = 0.0
    if last_nums:
        rep = 1.0 if number in last_nums else 0.0
        adj = 1.0 if any(abs(number - x) == 1 for x in last_nums) else 0.0
    tail = _tail_one_hot(number)
    zb = _zone_one_hot(number, zone)
    sc = _sum_contrib_proxy(number, sum_target) if zone == "front" else 0.0
    sp = _span_contrib_proxy(number, span_target, median_ball) if zone == "front" else 0.0
    z30 = 0.0
    if len(freq30_list) >= 2:
        mu = float(np.mean(freq30_list))
        sigma = float(np.std(freq30_list))
        if sigma >= 1e-8:
            z30 = (f30 - mu) / sigma
    hc = _hot_cold_tag_from_z(z30)
    li = _last_issue_interference(last_front, number, zone)
    return {
        "freq_10": f10,
        "freq_30": f30,
        "freq_50": f50,
        "freq_100": f100,
        "miss_current": miss,
        "ewma_hotness": ewma,
        "adjacent_last": adj,
        "repeat_last": rep,
        "tail_bucket": tail.tolist(),
        "zone_bucket": zb.tolist(),
        "sum_contrib_proxy": sc,
        "span_contrib_proxy": sp,
        "hot_cold_tag": hc,
        "last_issue_interference": li,
        "feature_vector": [],  # filled after standardize
    }


def flatten_feature_vector(d: dict[str, Any], std_vec: np.ndarray | None = None) -> np.ndarray:
    parts: list[float] = []
    keys = FEATURE_NAMES_NUMERIC
    for k in keys:
        parts.append(float(d[k]))
    parts.extend(d["tail_bucket"])
    parts.extend(d["zone_bucket"])
    arr = np.array(parts, dtype=np.float64)
    if std_vec is not None:
        arr = arr * std_vec
    return arr


def compute_feature_stats(
    all_vectors: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    if not all_vectors:
        return np.array([]), np.array([])
    m = np.vstack(all_vectors)
    mu = m.mean(axis=0)
    sigma = m.std(axis=0)
    sigma = np.where(sigma < 1e-8, 0.0, sigma)
    inv_sigma = np.where(sigma < 1e-8, 0.0, 1.0 / sigma)
    std_scale = np.ones_like(mu)
    for i in range(mu.size):
        if sigma[i] >= 1e-8:
            std_scale[i] = inv_sigma[i]
    return mu, std_scale


def standardize_vector(vec: np.ndarray, mu: np.ndarray, inv_sigma: np.ndarray) -> np.ndarray:
    out = vec.copy()
    for i in range(len(out)):
        if inv_sigma[i] == 0.0:
            out[i] = 0.0
        else:
            out[i] = (vec[i] - mu[i]) * inv_sigma[i]
    return out


def build_features_for_draws(
    draws: list[dict[str, Any]],
    model_version: str,
    persist: bool = True,
    ablate_groups: list[str] | None = None,
) -> tuple[dict[str, dict[int, dict[str, Any]]], dict[str, Any], str]:
    """
    Returns:
      features_by_zone: {"front": {n: feature_dict}, "back": {n: ...}}
      feature_summary: global stats + hashes
      feature_stats_hash
    """
    if not draws:
        return {"front": {}, "back": {}}, {"n_hist": 0, "draws_used": 0}, ""

    last = draws[-1]
    last_front = list(last.get("front", []))
    last_back = list(last.get("back", []))
    sum_target, span_target, median_ball = _sum_span_targets(draws)

    freq30_front = []
    for n in range(1, 36):
        freq30_front.append(_freq_in_window(draws, n, "front", 30))
    freq30_back = []
    for n in range(1, 13):
        freq30_back.append(_freq_in_window(draws, n, "back", 30))

    raw_front: dict[int, dict[str, Any]] = {}
    raw_back: dict[int, dict[str, Any]] = {}
    flat_list: list[np.ndarray] = []

    ablate_set = set(ablate_groups or [])
    for n in range(1, 36):
        d = raw_feature_dict(n, "front", draws, freq30_front, last_front, last_back, sum_target, span_target, median_ball)
        if ablate_set:
            d = _apply_feature_ablation_raw(d, ablate_set)
        raw_front[n] = d
        flat_list.append(
            flatten_feature_vector({**d, "tail_bucket": d["tail_bucket"], "zone_bucket": d["zone_bucket"]})
        )
    for n in range(1, 13):
        d = raw_feature_dict(n, "back", draws, freq30_back, last_front, last_back, sum_target, span_target, median_ball)
        if ablate_set:
            d = _apply_feature_ablation_raw(d, ablate_set)
        raw_back[n] = d
        flat_list.append(
            flatten_feature_vector({**d, "tail_bucket": d["tail_bucket"], "zone_bucket": d["zone_bucket"]})
        )

    mu, scale = compute_feature_stats(flat_list)
    inv_sigma = np.zeros_like(mu)
    for i in range(mu.size):
        if scale[i] > 0:
            inv_sigma[i] = scale[i]

    def finalize(d: dict[str, Any]) -> dict[str, Any]:
        base = flatten_feature_vector(d)
        std = standardize_vector(base, mu, inv_sigma)
        d = {**d, "feature_vector": std.tolist()}
        return d

    front_done = {n: finalize(dict(raw_front[n])) for n in raw_front}
    back_done = {n: finalize(dict(raw_back[n])) for n in raw_back}

    stats_payload = {
        "model_version": model_version,
        "mu": mu.tolist(),
        "inv_sigma": inv_sigma.tolist(),
        "dim": int(mu.size),
    }
    feature_stats_hash = sha256_hex(canonical_json_bytes(stats_payload))

    if persist:
        import json

        path = artifacts_backtests_dir() / f"feature_stats_{model_version}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(stats_payload, f, ensure_ascii=False, indent=2)

    feature_summary: dict[str, Any] = {
        "n_hist": len(draws),
        "draws_used": len(draws),
        "sum_target_median": sum_target,
        "span_target_median": span_target,
        "median_front_ball": median_ball,
        "feature_dim": int(mu.size),
        "feature_stats_hash": feature_stats_hash,
    }

    return {"front": front_done, "back": back_done}, feature_summary, feature_stats_hash


def load_issues_dataframe(issues: list[dict[str, Any]], target_issue: str | None, n_hist: int) -> list[dict[str, Any]]:
    chrono = _sorted_issues_chrono(issues)
    if target_issue and target_issue != "next":
        chrono = [x for x in chrono if str(x["issue"]) < str(target_issue)]
    return _window_issues(chrono, n_hist)
