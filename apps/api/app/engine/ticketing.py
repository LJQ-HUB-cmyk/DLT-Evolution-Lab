from __future__ import annotations

import itertools
from typing import Any

import numpy as np

from app.engine.search import (
    beam_search_tickets,
    hard_violation_back,
    hard_violation_front,
    soft_structure_score,
)
from app.models.schemas import Ticket


def _cal_prob_for_front(calibrated: dict[str, Any], pos_idx: int, n: int) -> float:
    for t in calibrated["front"][pos_idx]["top_numbers"]:
        if t["number"] == n:
            return max(1e-9, float(t["calibrated_prob"]))
    return 1e-9


def _cal_prob_for_back(calibrated: dict[str, Any], pos_idx: int, n: int) -> float:
    for t in calibrated["back"][pos_idx]["top_numbers"]:
        if t["number"] == n:
            return max(1e-9, float(t["calibrated_prob"]))
    return 1e-9


def min_calibrated_product(
    front: list[int],
    back: list[int],
    calibrated: dict[str, Any],
) -> float:
    fs = sorted(front)
    bs = sorted(back)
    probs = []
    for i, n in enumerate(fs):
        probs.append(_cal_prob_for_front(calibrated, i, n))
    for i, n in enumerate(bs):
        probs.append(_cal_prob_for_back(calibrated, i, n))
    return float(np.prod(probs) ** (1.0 / len(probs)))


def pick_stability_ticket(
    pool: list[tuple[list[int], list[int], float]],
    calibrated: dict[str, Any],
) -> tuple[list[int], list[int]] | None:
    best = None
    best_score = -1.0
    for f, b, _ in pool:
        if hard_violation_front(f) or hard_violation_back(b):
            continue
        sc = min_calibrated_product(f, b, calibrated)
        if sc > best_score:
            best_score = sc
            best = (list(sorted(f)), list(sorted(b)))
    return best


def build_plan1(
    calibrated: dict[str, Any],
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
    anchor_front: list[int] | None,
    anchor_back: list[int] | None,
    model_config: dict[str, Any],
) -> tuple[list[Ticket], dict[str, Any]]:
    search_cfg = model_config.get("search", {})
    beam = int(search_cfg.get("beam_width", 32))
    kf = int(search_cfg.get("k_front", 12))
    kb = int(search_cfg.get("k_back", 6))
    sw1 = model_config.get("structure", {}).get("plan1", {})

    tickets: list[Ticket] = []
    used: list[tuple[list[int], list[int]]] = []
    meta_used: dict[str, Any] = {}

    if anchor_front and anchor_back and len(anchor_front) == 5 and len(anchor_back) == 2:
        af = sorted(anchor_front)
        ab = sorted(anchor_back)
        if not hard_violation_front(af) and not hard_violation_back(ab):
            sc = soft_structure_score(af, ab, sw1, feats_by_zone)
            tickets.append(Ticket(front=af, back=ab, score=float(sc), tags=["plan1", "anchor"]))
            used.append((af, ab))

    if not tickets:
        pool, meta = beam_search_tickets(
            calibrated,
            feats_by_zone,
            beam_width=beam,
            k_front=kf,
            k_back=kb,
            structure_weights=sw1,
            max_tickets=24,
            existing=[],
        )
        meta_used = meta.as_dict()
        stab = pick_stability_ticket(pool, calibrated)
        if stab:
            f, b = stab
            sc = soft_structure_score(f, b, sw1, feats_by_zone)
            tickets.append(Ticket(front=f, back=b, score=float(sc), tags=["plan1", "anchor", "computed"]))
            used.append((f, b))

    # Iterative greedy ranking: after each selected ticket, recompute best next ticket under diversity constraints.
    while len(tickets) < 5:
        rest_pool, meta = beam_search_tickets(
            calibrated,
            feats_by_zone,
            beam_width=beam,
            k_front=kf,
            k_back=kb,
            structure_weights=sw1,
            max_tickets=40,
            existing=used,
        )
        meta_used = meta.as_dict()
        picked = None
        for f, b, tot in rest_pool:
            f, b = sorted(f), sorted(b)
            if hard_violation_front(f) or hard_violation_back(b):
                continue
            if (tuple(f), tuple(b)) in {(tuple(x.front), tuple(x.back)) for x in tickets}:
                continue
            picked = (f, b, tot)
            break
        if picked is None:
            break
        f, b, tot = picked
        tickets.append(Ticket(front=f, back=b, score=float(tot), tags=["plan1", "structured"]))
        used.append((f, b))

    if not tickets:
        return [], meta_used

    # Keep anchor first; remaining structured groups sorted by score high -> low.
    anchor_ticket = tickets[0]
    tail = sorted(tickets[1:], key=lambda t: float(t.score), reverse=True)
    return [anchor_ticket, *tail][:5], meta_used


def build_plan2(
    calibrated: dict[str, Any],
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
    model_config: dict[str, Any],
    rng: np.random.Generator,
    plan1_tickets: list[Ticket] | None = None,
) -> tuple[list[Ticket], dict[str, Any]]:
    search_cfg = model_config.get("search", {})
    beam = int(search_cfg.get("beam_width", 28))
    kf = int(search_cfg.get("k_front", 12))
    kb = int(search_cfg.get("k_back", 6))
    sw2_base = model_config.get("structure", {}).get("plan2", {"odd_even": 0.6, "zone_balance": 0.8})
    # Plan2 intentionally weakens structure constraints to avoid converging to plan1.
    sw2 = {k: float(v) * 0.55 for k, v in sw2_base.items()}
    p1 = plan1_tickets or []

    tickets: list[Ticket] = []
    seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    _ = rng
    meta_used: dict[str, Any] = {}
    strict_skipped = 0
    fallback_rounds = 0

    def _diff_penalty(f: list[int], b: list[int]) -> float:
        if not p1:
            return 0.0
        fset = set(f)
        bset = set(b)
        best = 0.0
        for t in p1:
            tf = set(t.front)
            tb = set(t.back)
            fj = len(fset & tf) / (len(fset | tf) or 1)
            bj = len(bset & tb) / (len(bset | tb) or 1)
            # Strongly penalize high front overlap and exact back overlap.
            same_back = 1.0 if bset == tb else 0.0
            cur = 2.8 * fj + 1.4 * bj + 1.2 * same_back
            if cur > best:
                best = cur
        return best

    def _too_close_to_plan1(f: list[int], b: list[int]) -> bool:
        if not p1:
            return False
        fset = set(f)
        bset = set(b)
        for t in p1:
            fi = len(fset & set(t.front))
            bi = len(bset & set(t.back))
            if fi >= 5:
                return True
            if fi >= 4 and bi >= 1:
                return True
            if bset == set(t.back):
                return True
        return False

    if p1:
        front_prob = _top_prob_map(calibrated, "front")
        back_prob = _top_prob_map(calibrated, "back")
        ranked_front = sorted(range(1, 36), key=lambda n: front_prob.get(n, 0.0), reverse=True)
        ranked_back = sorted(range(1, 13), key=lambda n: back_prob.get(n, 0.0), reverse=True)
        mtickets: list[Ticket] = []
        mseen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()

        for base in p1:
            if len(mtickets) >= 5:
                break
            bf = sorted(base.front)
            bb = sorted(base.back)
            picked = None
            for old in bf:
                for cand in ranked_front[:16]:
                    if cand in bf:
                        continue
                    nf = sorted([x for x in bf if x != old] + [cand])
                    if hard_violation_front(nf):
                        continue
                    if _too_close_to_plan1(nf, bb):
                        continue
                    for oldb in bb:
                        for candb in ranked_back[:10]:
                            if candb in bb:
                                continue
                            nb = sorted([x for x in bb if x != oldb] + [candb])
                            if hard_violation_back(nb):
                                continue
                            if _too_close_to_plan1(nf, nb):
                                continue
                            key = (tuple(nf), tuple(nb))
                            if key in mseen:
                                continue
                            ll = sum(np.log(max(1e-9, front_prob.get(x, 1e-9))) for x in nf) + sum(
                                np.log(max(1e-9, back_prob.get(x, 1e-9))) for x in nb
                            )
                            score = ll + 0.2 * soft_structure_score(nf, nb, sw2, feats_by_zone) - _diff_penalty(nf, nb)
                            picked = Ticket(
                                front=nf,
                                back=nb,
                                score=float(score),
                                tags=["plan2", "mutated", "anti_plan1_overlap"],
                            )
                            mseen.add(key)
                            break
                        if picked is not None:
                            break
                    if picked is not None:
                        break
                if picked is not None:
                    break
            if picked is not None:
                mtickets.append(picked)

        if len(mtickets) >= 5:
            meta = {
                "beam_width": beam,
                "candidate_count_front": kf * 5,
                "candidate_count_back": kb * 2,
                "pruned_count": 0,
                "structure_scale": 0.55,
                "plan1_difference_penalty": "enabled",
                "plan1_hard_separation": "mutate_from_plan1",
                "plan1_count": len(p1),
                "strict_skipped": 0,
                "fallback_rounds": 0,
            }
            return sorted(mtickets[:5], key=lambda t: float(t.score), reverse=True), meta

    # Iterative greedy ranking for plan2 (light constraints + explicit anti-overlap with plan1).
    while len(tickets) < 5:
        existing = [(list(k[0]), list(k[1])) for k in seen]
        pool, meta = beam_search_tickets(
            calibrated,
            feats_by_zone,
            beam_width=beam,
            k_front=kf,
            k_back=kb,
            structure_weights=sw2,
            max_tickets=30,
            existing=existing,
        )
        meta_used = meta.as_dict()
        picked = None
        picked_adj = float("-inf")
        for f, b, tot in pool:
            f, b = sorted(f), sorted(b)
            if hard_violation_front(f) or hard_violation_back(b):
                continue
            key = (tuple(f), tuple(b))
            if key in seen:
                continue
            if _too_close_to_plan1(f, b):
                strict_skipped += 1
                continue
            adj = float(tot) - _diff_penalty(f, b)
            if adj > picked_adj:
                picked = (f, b, adj)
                picked_adj = adj
        if picked is None:
            fallback_rounds += 1
            # Fallback: keep anti-overlap soft penalty but relax hard separation to avoid empty plan2.
            for f, b, tot in pool:
                f, b = sorted(f), sorted(b)
                if hard_violation_front(f) or hard_violation_back(b):
                    continue
                key = (tuple(f), tuple(b))
                if key in seen:
                    continue
                if any(set(f) == set(t.front) for t in p1):
                    continue
                if any(set(b) == set(t.back) for t in p1):
                    continue
                adj = float(tot) - 0.5 * _diff_penalty(f, b)
                if adj > picked_adj:
                    picked = (f, b, adj)
                    picked_adj = adj
        if picked is None:
            break
        f, b, tot = picked
        seen.add((tuple(f), tuple(b)))
        tickets.append(Ticket(front=f, back=b, score=float(tot), tags=["plan2", "ranked", "anti_plan1_overlap"]))

    # Fast fallback: mutate plan1 tickets to guarantee usable and visibly different plan2 output.
    if len(tickets) < 5 and p1:
        front_prob = _top_prob_map(calibrated, "front")
        back_prob = _top_prob_map(calibrated, "back")
        ranked_front = sorted(range(1, 36), key=lambda n: front_prob.get(n, 0.0), reverse=True)
        ranked_back = sorted(range(1, 13), key=lambda n: back_prob.get(n, 0.0), reverse=True)

        for base in p1:
            if len(tickets) >= 5:
                break
            base_f = sorted(base.front)
            base_b = sorted(base.back)
            chosen = None
            for old in base_f:
                for cand in ranked_front[:14]:
                    if cand in base_f:
                        continue
                    nf = sorted([x for x in base_f if x != old] + [cand])
                    if hard_violation_front(nf):
                        continue
                    if _too_close_to_plan1(nf, base_b):
                        continue
                    for old_b in base_b:
                        for cand_b in ranked_back[:10]:
                            if cand_b in base_b:
                                continue
                            nb = sorted([x for x in base_b if x != old_b] + [cand_b])
                            if hard_violation_back(nb):
                                continue
                            if _too_close_to_plan1(nf, nb):
                                continue
                            key = (tuple(nf), tuple(nb))
                            if key in seen:
                                continue
                            ll = sum(np.log(max(1e-9, front_prob.get(x, 1e-9))) for x in nf) + sum(
                                np.log(max(1e-9, back_prob.get(x, 1e-9))) for x in nb
                            )
                            adj = float(ll) - 0.8 * _diff_penalty(nf, nb)
                            chosen = (nf, nb, adj)
                            break
                        if chosen is not None:
                            break
                    if chosen is not None:
                        break
                if chosen is not None:
                    break
            if chosen is None:
                continue
            nf, nb, adj = chosen
            seen.add((tuple(nf), tuple(nb)))
            tickets.append(Ticket(front=nf, back=nb, score=float(adj), tags=["plan2", "fallback_mutation"]))

    tickets = sorted(tickets, key=lambda t: float(t.score), reverse=True)
    meta_used["structure_scale"] = 0.55
    meta_used["plan1_difference_penalty"] = "enabled"
    meta_used["plan1_hard_separation"] = "not_exact_front_and_not_high_front_with_shared_back"
    meta_used["plan1_count"] = len(p1)
    meta_used["strict_skipped"] = strict_skipped
    meta_used["fallback_rounds"] = fallback_rounds
    return tickets[:5], meta_used


def _top_prob_map(calibrated: dict[str, Any], zone: str) -> dict[int, float]:
    out: dict[int, float] = {}
    blocks = calibrated.get(zone, [])
    for block in blocks:
        for t in block.get("top_numbers", []):
            n = int(t.get("number"))
            p = float(t.get("calibrated_prob", 0.0))
            if p > out.get(n, 0.0):
                out[n] = p
    return out


def _zone_idx_front(n: int) -> int:
    if 1 <= n <= 12:
        return 0
    if 13 <= n <= 24:
        return 1
    return 2


def _max_consecutive(sorted_nums: list[int]) -> int:
    if not sorted_nums:
        return 0
    cur = 1
    best = 1
    for i in range(1, len(sorted_nums)):
        if sorted_nums[i] == sorted_nums[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def _tail_dup_groups(nums: list[int]) -> int:
    counts: dict[int, int] = {}
    for n in nums:
        k = n % 10
        counts[k] = counts.get(k, 0) + 1
    return sum(1 for v in counts.values() if v >= 2)


def _classify_hot_cold(feats_by_zone: dict[str, dict[int, dict[str, Any]]]) -> tuple[set[int], set[int], set[int]]:
    vals = []
    for n in range(1, 36):
        f = feats_by_zone.get("front", {}).get(n, {})
        vals.append(float(f.get("freq_30", 0.0)))
    if not vals:
        return set(), set(), set(range(1, 36))
    q1 = float(np.quantile(vals, 0.33))
    q2 = float(np.quantile(vals, 0.67))
    hot: set[int] = set()
    cold: set[int] = set()
    warm: set[int] = set()
    for n in range(1, 36):
        v = float(feats_by_zone.get("front", {}).get(n, {}).get("freq_30", 0.0))
        if v >= q2:
            hot.add(n)
        elif v <= q1:
            cold.add(n)
        else:
            warm.add(n)
    return hot, cold, warm


def _pass_structured_front_rules(front: list[int], hot: set[int], cold: set[int], warm: set[int]) -> bool:
    fs = sorted(front)
    if len(fs) != 5 or len(set(fs)) != 5:
        return False
    big = sum(1 for x in fs if x >= 18)
    odd = sum(1 for x in fs if x % 2 == 1)
    if big not in (2, 3):
        return False
    if odd not in (2, 3):
        return False
    z = [0, 0, 0]
    for x in fs:
        z[_zone_idx_front(x)] += 1
    if min(z) <= 0:
        return False
    if tuple(sorted(z)) not in {(1, 1, 3), (1, 2, 2)}:
        return False
    h = sum(1 for x in fs if x in hot)
    c = sum(1 for x in fs if x in cold)
    w = sum(1 for x in fs if x in warm)
    if h < 2 or h > 3:
        return False
    if c < 1 or c > 2:
        return False
    if w < 1 or w > 2:
        return False
    if _max_consecutive(fs) >= 3:
        return False
    if _tail_dup_groups(fs) > 1:
        return False
    span = fs[-1] - fs[0]
    if span < 10 or span > 30:
        return False
    return True


def _pass_structured_back_rules(back: list[int]) -> bool:
    bs = sorted(back)
    if len(bs) != 2 or len(set(bs)) != 2:
        return False
    small = sum(1 for x in bs if x <= 6)
    odd = sum(1 for x in bs if x % 2 == 1)
    if small != 1:
        return False
    if odd != 1:
        return False
    if abs(bs[1] - bs[0]) == 1:
        return False
    if bs[0] % 10 == bs[1] % 10:
        return False
    return True


def _pass_xuanxue_light_front(front: list[int]) -> bool:
    fs = sorted(front)
    odd = sum(1 for x in fs if x % 2 == 1)
    big = sum(1 for x in fs if x >= 18)
    if odd in (0, 5):
        return False
    if big in (0, 5):
        return False
    z = [0, 0, 0]
    for x in fs:
        z[_zone_idx_front(x)] += 1
    if min(z) <= 0:
        return False
    if _max_consecutive(fs) >= 3:
        return False
    return True


def _pass_xuanxue_light_back(back: list[int]) -> bool:
    bs = sorted(back)
    odd = sum(1 for x in bs if x % 2 == 1)
    small = sum(1 for x in bs if x <= 6)
    if odd in (0, 2):
        return False
    if small in (0, 2):
        return False
    if abs(bs[1] - bs[0]) == 1:
        return False
    return True


def build_plan3(
    calibrated: dict[str, Any],
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
) -> tuple[list[Ticket], dict[str, Any]]:
    front_prob = _top_prob_map(calibrated, "front")
    back_prob = _top_prob_map(calibrated, "back")

    hot, cold, warm = _classify_hot_cold(feats_by_zone)

    front_base = sorted(
        list({n for n in range(1, 36) if (front_prob.get(n, 0.0) > 0)}),
        key=lambda n: front_prob.get(n, 0.0),
        reverse=True,
    )
    if len(front_base) < 18:
        missing = [n for n in range(1, 36) if n not in set(front_base)]
        front_base.extend(missing)
    front_pool = sorted(front_base[:20])
    back_pool = sorted(
        list({n for n in range(1, 13) if back_prob.get(n, 0.0) > 0}) or list(range(1, 13)),
        key=lambda n: back_prob.get(n, 0.0),
        reverse=True,
    )[:10]
    back_pool = sorted(set(back_pool))

    structured_fronts: list[tuple[list[int], float]] = []
    for combo in itertools.combinations(front_pool, 5):
        f = list(combo)
        if not _pass_structured_front_rules(f, hot, cold, warm):
            continue
        fs = sorted(f)
        z = [0, 0, 0]
        for x in fs:
            z[_zone_idx_front(x)] += 1
        zone_balance_bonus = 1.0 - (max(z) - min(z)) / 3.0
        s = sum(np.log(max(1e-9, front_prob.get(x, 1e-9))) for x in fs) + 1.2 * zone_balance_bonus
        structured_fronts.append((fs, float(s)))
    structured_fronts.sort(key=lambda x: x[1], reverse=True)

    structured_backs: list[tuple[list[int], float]] = []
    for combo in itertools.combinations(back_pool, 2):
        b = list(combo)
        if not _pass_structured_back_rules(b):
            continue
        s = sum(np.log(max(1e-9, back_prob.get(x, 1e-9))) for x in b)
        structured_backs.append((sorted(b), float(s)))
    structured_backs.sort(key=lambda x: x[1], reverse=True)

    tickets: list[Ticket] = []
    seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    structured_target = 3
    for ff, sf in structured_fronts[:80]:
        for bb, sb in structured_backs[:40]:
            key = (tuple(ff), tuple(bb))
            if key in seen:
                continue
            seen.add(key)
            score = sf + sb
            tickets.append(Ticket(front=ff, back=bb, score=float(score), tags=["plan3", "stats_aesthetic"]))
            if len([t for t in tickets if "stats_aesthetic" in t.tags]) >= structured_target:
                break
        if len([t for t in tickets if "stats_aesthetic" in t.tags]) >= structured_target:
            break

    lucky_front = {1, 3, 6, 8, 9, 11, 16, 18, 21, 24, 28, 33}
    lucky_back = {1, 3, 6, 8, 9, 11}
    xuanxue_front_base = sorted(
        set(front_pool[:14]).union(lucky_front),
        key=lambda n: (1 if n in lucky_front else 0, front_prob.get(n, 0.0)),
        reverse=True,
    )
    xuanxue_front_pool = sorted(xuanxue_front_base[:18])
    xuanxue_back_base = sorted(
        set(back_pool[:8]).union(lucky_back),
        key=lambda n: (1 if n in lucky_back else 0, back_prob.get(n, 0.0)),
        reverse=True,
    )
    xuanxue_back_pool = sorted(xuanxue_back_base[:10])

    xuanxue_candidates: list[Ticket] = []
    for f in itertools.combinations(xuanxue_front_pool, 5):
        ff = sorted(list(f))
        if not _pass_xuanxue_light_front(ff):
            continue
        lucky_hit = sum(1 for x in ff if x in lucky_front)
        model_support = sum(np.log(max(1e-9, front_prob.get(x, 1e-9))) for x in ff)
        for b in itertools.combinations(xuanxue_back_pool, 2):
            bb = sorted(list(b))
            if not _pass_xuanxue_light_back(bb):
                continue
            key = (tuple(ff), tuple(bb))
            if key in seen:
                continue
            lucky_back_hit = sum(1 for x in bb if x in lucky_back)
            back_support = sum(np.log(max(1e-9, back_prob.get(x, 1e-9))) for x in bb)
            score = 2.0 * (lucky_hit + lucky_back_hit) + 0.4 * (model_support + back_support)
            xuanxue_candidates.append(
                Ticket(front=ff, back=bb, score=float(score), tags=["plan3", "xuanxue_light"])
            )
    xuanxue_candidates.sort(key=lambda t: float(t.score), reverse=True)

    for t in xuanxue_candidates:
        key = (tuple(t.front), tuple(t.back))
        if key in seen:
            continue
        seen.add(key)
        tickets.append(t)
        if len(tickets) >= 5:
            break

    tickets = tickets[:5]
    meta = {
        "front_pool_size": len(front_pool),
        "back_pool_size": len(back_pool),
        "structured_front_candidates": len(structured_fronts),
        "structured_back_candidates": len(structured_backs),
        "xuanxue_candidates": len(xuanxue_candidates),
        "rules": [
            "size_ratio_2_3_or_3_2",
            "odd_even_ratio_2_3_or_3_2",
            "three_zone_coverage",
            "hot_warm_cold_mix",
            "no_extreme_shape",
            "xuanxue_plus_light_constraints",
        ],
    }
    return tickets, meta
