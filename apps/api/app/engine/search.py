from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _is_all_odd(nums: list[int]) -> bool:
    return all(n % 2 == 1 for n in nums)


def _is_all_even(nums: list[int]) -> bool:
    return all(n % 2 == 0 for n in nums)


def _is_all_small(nums: list[int]) -> bool:
    return all(n <= 17 for n in nums)


def _is_all_big(nums: list[int]) -> bool:
    return all(n >= 18 for n in nums)


def _max_consecutive_run(sorted_nums: list[int]) -> int:
    if len(sorted_nums) < 2:
        return 1
    best = 1
    cur = 1
    for i in range(1, len(sorted_nums)):
        if sorted_nums[i] == sorted_nums[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def hard_violation_front(front: list[int]) -> bool:
    if len(front) != 5:
        return True
    if len(set(front)) != 5:
        return True
    if not all(1 <= n <= 35 for n in front):
        return True
    s = sorted(front)
    if _is_all_odd(s) or _is_all_even(s):
        return True
    if _is_all_small(s) or _is_all_big(s):
        return True
    if _max_consecutive_run(s) >= 4:
        return True
    return False


def hard_violation_back(back: list[int]) -> bool:
    if len(back) != 2:
        return True
    if len(set(back)) != 2:
        return True
    if not all(1 <= n <= 12 for n in back):
        return True
    return False


def soft_structure_score(
    front: list[int],
    back: list[int],
    weights: dict[str, float],
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
) -> float:
    fs = sorted(front)
    odd = sum(1 for x in fs if x % 2 == 1)
    big = sum(1 for x in fs if x >= 18)
    odd_even_score = 1.0 - abs(odd - 2.5) / 2.5
    big_small_score = 1.0 - abs(big - 2.5) / 2.5
    zc = [0, 0, 0]
    for x in fs:
        if 1 <= x <= 12:
            zc[0] += 1
        elif 13 <= x <= 24:
            zc[1] += 1
        else:
            zc[2] += 1
    zone_balance_score = 1.0 - (max(zc) - min(zc)) / 5.0
    ssum = sum(fs)
    span = fs[-1] - fs[0]
    sum_band_score = 1.0 - min(1.0, abs(ssum - 95) / 40.0)
    span_band_score = 1.0 - min(1.0, abs(span - 18) / 18.0)
    hc_vals = [feats_by_zone["front"][n]["hot_cold_tag"] for n in fs]
    hot_cold_mix_score = 1.0 - abs(sum(hc_vals)) / 5.0
    w = weights
    return (
        w.get("odd_even", 1.0) * odd_even_score
        + w.get("big_small", 1.0) * big_small_score
        + w.get("zone_balance", 1.0) * zone_balance_score
        + w.get("sum_band", 0.8) * sum_band_score
        + w.get("span_band", 0.8) * span_band_score
        + w.get("hot_cold_mix", 0.6) * hot_cold_mix_score
    )


def _cands_for_position(calibrated: dict[str, Any], zone: str, pos_idx: int, k: int) -> list[int]:
    block = calibrated[zone][pos_idx]
    tops = block["top_numbers"][:k]
    return [int(t["number"]) for t in tops]


def _logp_for(calibrated: dict[str, Any], zone: str, pos_idx: int, n: int) -> float:
    block = calibrated[zone][pos_idx]
    for t in block["top_numbers"]:
        if t["number"] == n:
            p = max(1e-9, float(t["calibrated_prob"]))
            return float(np.log(p))
    return -12.0


def diversity_penalty(
    front: list[int],
    back: list[int],
    existing: list[tuple[list[int], list[int]]],
    jaccard_thr: float = 0.8,
) -> float:
    if not existing:
        return 0.0
    fset = set(front)
    pen = 0.0
    for ef, eb in existing:
        inter = len(fset & set(ef))
        union = len(fset | set(ef)) or 1
        j = inter / union
        if j > jaccard_thr:
            pen += 2.0 * (j - jaccard_thr)
        if set(back) == set(eb):
            pen += 1.5
    return pen


@dataclass
class SearchMeta:
    beam_width: int
    candidate_count_front: int
    candidate_count_back: int
    pruned_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "beam_width": self.beam_width,
            "candidate_count_front": self.candidate_count_front,
            "candidate_count_back": self.candidate_count_back,
            "pruned_count": self.pruned_count,
        }


def beam_search_tickets(
    calibrated: dict[str, Any],
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
    *,
    beam_width: int = 32,
    k_front: int = 12,
    k_back: int = 6,
    structure_weights: dict[str, float] | None = None,
    max_tickets: int = 5,
    existing: list[tuple[list[int], list[int]]] | None = None,
) -> tuple[list[tuple[list[int], list[int], float]], SearchMeta]:
    sw = structure_weights or {}
    existing = existing or []
    pruned = 0

    front_cands = [_cands_for_position(calibrated, "front", i, k_front) for i in range(5)]
    back_cands = [_cands_for_position(calibrated, "back", i, k_back) for i in range(2)]

    # partial front: list of (tuple front, logpos_score)
    states: list[tuple[tuple[int, ...], float]] = [(tuple(), 0.0)]
    for pos in range(5):
        nxt: list[tuple[tuple[int, ...], float]] = []
        last_min = 0
        for partial, sc in states:
            last_min = partial[-1] if partial else 0
            for n in front_cands[pos]:
                if n <= last_min:
                    continue
                nf = partial + (n,)
                if pos == 4 and hard_violation_front(list(nf)):
                    pruned += 1
                    continue
                nxt.append((nf, sc + _logp_for(calibrated, "front", pos, n)))
        nxt.sort(key=lambda x: -x[1])
        states = nxt[: max(1, beam_width * 4)]

    completed_front = states[: max(1, beam_width * 8)]

    finals: list[tuple[list[int], list[int], float]] = []
    for f_tuple, fsc in completed_front:
        if len(f_tuple) != 5:
            continue
        if hard_violation_front(list(f_tuple)):
            pruned += 1
            continue
        b_states: list[tuple[tuple[int, ...], float]] = [(tuple(), 0.0)]
        for pos in range(2):
            bnxt: list[tuple[tuple[int, ...], float]] = []
            for partial, sc in b_states:
                last_min = partial[-1] if partial else 0
                for n in back_cands[pos]:
                    if n <= last_min:
                        continue
                    nb = partial + (n,)
                    bnxt.append((nb, sc + _logp_for(calibrated, "back", pos, n)))
            bnxt.sort(key=lambda x: -x[1])
            b_states = bnxt[:beam_width]
        for b_tuple, bsc in b_states:
            if len(b_tuple) != 2:
                continue
            front = list(f_tuple)
            back = list(b_tuple)
            if hard_violation_back(back):
                pruned += 1
                continue
            struct = soft_structure_score(front, back, sw, feats_by_zone)
            div_pen = diversity_penalty(front, back, existing + [(f, b) for f, b, _ in finals])
            total = fsc + bsc + struct - div_pen
            if hard_violation_front(front):
                continue
            finals.append((front, back, float(total)))

    finals.sort(key=lambda x: -x[2])
    uniq: list[tuple[list[int], list[int], float]] = []
    seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    for f, b, s in finals:
        key = (tuple(sorted(f)), tuple(sorted(b)))
        if key in seen:
            continue
        seen.add(key)
        uniq.append((f, b, s))
        if len(uniq) >= max_tickets * 4:
            break

    uniq = uniq[:max_tickets]

    meta = SearchMeta(
        beam_width=beam_width,
        candidate_count_front=k_front * 5,
        candidate_count_back=k_back * 2,
        pruned_count=pruned,
    )
    return uniq, meta


def ticket_from_pool(
    pool: list[tuple[list[int], list[int], float]],
    rng: np.random.Generator,
    weights: dict[str, float],
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
) -> tuple[list[int], list[int]] | None:
    if not pool:
        return None
    scores = np.array([max(0.01, t[2]) for t in pool], dtype=np.float64)
    p = scores / scores.sum()
    idx = int(rng.choice(len(pool), p=p))
    f, b, _ = pool[idx]
    if hard_violation_front(f) or hard_violation_back(b):
        return None
    return f, b
