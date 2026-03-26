from __future__ import annotations

from typing import Any

import numpy as np

from app.engine.search import (
    beam_search_tickets,
    hard_violation_back,
    hard_violation_front,
    soft_structure_score,
    ticket_from_pool,
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

    tickets: list[Ticket] = []
    used: list[tuple[list[int], list[int]]] = []

    if anchor_front and anchor_back and len(anchor_front) == 5 and len(anchor_back) == 2:
        af = sorted(anchor_front)
        ab = sorted(anchor_back)
        if not hard_violation_front(af) and not hard_violation_back(ab):
            sc = soft_structure_score(af, ab, sw1, feats_by_zone)
            tickets.append(Ticket(front=af, back=ab, score=float(sc), tags=["plan1", "anchor"]))
            used.append((af, ab))

    if not tickets:
        stab = pick_stability_ticket(pool, calibrated)
        if stab:
            f, b = stab
            sc = soft_structure_score(f, b, sw1, feats_by_zone)
            tickets.append(Ticket(front=f, back=b, score=float(sc), tags=["plan1", "anchor", "computed"]))
            used.append((f, b))

    rest_pool, _ = beam_search_tickets(
        calibrated,
        feats_by_zone,
        beam_width=beam,
        k_front=kf,
        k_back=kb,
        structure_weights=sw1,
        max_tickets=40,
        existing=used,
    )

    for f, b, tot in rest_pool:
        if len(tickets) >= 5:
            break
        f, b = sorted(f), sorted(b)
        if hard_violation_front(f) or hard_violation_back(b):
            continue
        if (tuple(f), tuple(b)) in {(tuple(x.front), tuple(x.back)) for x in tickets}:
            continue
        tickets.append(Ticket(front=f, back=b, score=float(tot), tags=["plan1", "structured"]))
        used.append((f, b))

    pi = 0
    while len(tickets) < 5 and pi < len(pool):
        f, b, tot = pool[pi]
        pi += 1
        f, b = sorted(f), sorted(b)
        if hard_violation_front(f) or hard_violation_back(b):
            continue
        if (tuple(f), tuple(b)) in {(tuple(x.front), tuple(x.back)) for x in tickets}:
            continue
        tickets.append(Ticket(front=f, back=b, score=float(tot), tags=["plan1", "fallback"]))

    return tickets[:5], meta.as_dict()


def build_plan2(
    calibrated: dict[str, Any],
    feats_by_zone: dict[str, dict[int, dict[str, Any]]],
    model_config: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[list[Ticket], dict[str, Any]]:
    search_cfg = model_config.get("search", {})
    beam = int(search_cfg.get("beam_width", 28))
    kf = int(search_cfg.get("k_front", 12))
    kb = int(search_cfg.get("k_back", 6))
    sw2 = model_config.get("structure", {}).get("plan2", {"odd_even": 0.6, "zone_balance": 0.8})

    pool, meta = beam_search_tickets(
        calibrated,
        feats_by_zone,
        beam_width=beam,
        k_front=kf,
        k_back=kb,
        structure_weights=sw2,
        max_tickets=30,
        existing=[],
    )

    tickets: list[Ticket] = []
    seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    attempts = 0
    while len(tickets) < 5 and attempts < 80:
        attempts += 1
        pick = ticket_from_pool(pool, rng, sw2, feats_by_zone)
        if pick is None:
            break
        f, b = pick
        f, b = sorted(f), sorted(b)
        if hard_violation_front(f) or hard_violation_back(b):
            continue
        key = (tuple(f), tuple(b))
        if key in seen:
            continue
        seen.add(key)
        sc = soft_structure_score(f, b, sw2, feats_by_zone)
        tickets.append(Ticket(front=f, back=b, score=float(sc), tags=["plan2", "sampled"]))

    idx = 0
    while len(tickets) < 5 and idx < len(pool):
        f, b, _ = pool[idx]
        idx += 1
        f, b = sorted(f), sorted(b)
        key = (tuple(f), tuple(b))
        if key in seen:
            continue
        if hard_violation_front(f) or hard_violation_back(b):
            continue
        seen.add(key)
        sc = soft_structure_score(f, b, sw2, feats_by_zone)
        tickets.append(Ticket(front=f, back=b, score=float(sc), tags=["plan2", "fill"]))

    return tickets[:5], meta.as_dict()
