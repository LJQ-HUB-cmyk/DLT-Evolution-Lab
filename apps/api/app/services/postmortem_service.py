from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from app.services.json_store import JsonStore

PrizeLevel = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9] | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_prize_level(front_hits: int, back_hits: int) -> PrizeLevel | Literal["no_prize"]:
    """M5 默认大乐透奖级映射。"""
    if front_hits == 5 and back_hits == 2:
        return 1
    if front_hits == 5 and back_hits == 1:
        return 2
    if front_hits == 5 and back_hits == 0:
        return 3
    if front_hits == 4 and back_hits == 2:
        return 4
    if front_hits == 4 and back_hits == 1:
        return 5
    if front_hits == 3 and back_hits == 2:
        return 6
    if front_hits == 4 and back_hits == 0:
        return 7
    if front_hits == 3 and back_hits == 1 or (front_hits == 2 and back_hits == 2):
        return 8
    if (
        (front_hits == 3 and back_hits == 0)
        or (front_hits == 2 and back_hits == 1)
        or (front_hits == 1 and back_hits == 2)
        or (front_hits == 0 and back_hits == 2)
    ):
        return 9
    return "no_prize"


def _ticket_hits(ticket: dict[str, Any], draw_front: list[int], draw_back: list[int]) -> tuple[int, int]:
    tf = set(ticket.get("front") or [])
    tb = set(ticket.get("back") or [])
    df = set(draw_front)
    db = set(draw_back)
    return len(tf & df), len(tb & db)


def _odd_even_structure(front: list[int]) -> tuple[int, int]:
    odds = sum(1 for n in front if n % 2 == 1)
    return odds, len(front) - odds


def _zone_buckets(front: list[int]) -> tuple[int, int, int]:
    """Zones 1-12, 13-24, 25-35."""
    z = [0, 0, 0]
    for n in front:
        if n <= 12:
            z[0] += 1
        elif n <= 24:
            z[1] += 1
        else:
            z[2] += 1
    return z[0], z[1], z[2]


def _sum_span(front: list[int]) -> tuple[int, int]:
    return sum(front), max(front) - min(front)


def structure_match_score(ticket: dict[str, Any], draw_front: list[int], draw_back: list[int]) -> float:
    """结构命中得分 0-100 简化版。"""
    tf = sorted(ticket.get("front") or [])
    if len(tf) != 5:
        return 0.0
    ddf = sorted(draw_front)
    o1, e1 = _odd_even_structure(tf)
    o2, e2 = _odd_even_structure(ddf)
    z1 = _zone_buckets(tf)
    z2 = _zone_buckets(ddf)
    s1, sp1 = _sum_span(tf)
    s2, sp2 = _sum_span(ddf)
    score = 0.0
    if abs(o1 - o2) <= 1:
        score += 25
    if sum(abs(a - b) for a, b in zip(z1, z2, strict=False)) <= 2:
        score += 25
    if abs(s1 - s2) <= 25:
        score += 25
    if abs(sp1 - sp2) <= 10:
        score += 25
    return score


def prize_level_to_score(level: PrizeLevel | Literal["no_prize"]) -> float:
    if level == "no_prize" or level is None:
        return 0.0
    weights = {1: 100.0, 2: 88.0, 3: 76.0, 4: 64.0, 5: 52.0, 6: 44.0, 7: 36.0, 8: 24.0, 9: 12.0}
    return weights.get(int(level), 0.0)


def stability_score_from_history(recent_scores: list[float]) -> float:
    if not recent_scores:
        return 50.0
    m = sum(recent_scores) / len(recent_scores)
    if len(recent_scores) == 1:
        return m
    var = sum((x - m) ** 2 for x in recent_scores) / len(recent_scores)
    penalty = min(40.0, var * 2.0)
    return max(0.0, 100.0 - penalty)


def compute_postmortem_aggregate(
    prize_score: float,
    structure_score: float,
    stability_score: float,
) -> float:
    return 0.6 * prize_score + 0.25 * structure_score + 0.15 * stability_score


def _find_draw_for_issue(store: JsonStore, issue: str) -> dict[str, Any] | None:
    issues = store.read("issues.json", default={"items": []})
    for row in issues.get("items", []):
        if str(row.get("issue")) == str(issue):
            return row
    return None


def _collect_runs_for_issue(store: JsonStore, issue: str) -> list[dict[str, Any]]:
    preds = store.read("predictions.json", default={"official": [], "experimental": []})
    out: list[dict[str, Any]] = []
    for o in preds.get("official", []):
        if str(o.get("target_issue")) == str(issue):
            out.append({**o, "_kind": "official"})
    for e in preds.get("experimental", []):
        if str(e.get("target_issue")) == str(issue):
            out.append({**e, "_kind": "experimental"})
    return out


def build_hit_matrix(draw: dict[str, Any], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = sorted(draw.get("front") or [])
    db = sorted(draw.get("back") or [])
    matrix: list[dict[str, Any]] = []
    for run in runs:
        rid = run.get("run_id")
        tickets: list[dict[str, Any]] = []
        for plan_key in ("plan1", "plan2", "plan3"):
            for idx, t in enumerate(run.get(plan_key) or []):
                fh, bh = _ticket_hits(t, df, db)
                level = map_prize_level(fh, bh)
                tickets.append(
                    {
                        "plan": plan_key,
                        "index": idx,
                        "front_hits": fh,
                        "back_hits": bh,
                        "prize_level": level,
                        "structure_score": structure_match_score(t, df, db),
                    }
                )
        best = None
        for t in tickets:
            pl = t["prize_level"]
            ps = prize_level_to_score(pl if pl != "no_prize" else "no_prize")
            if best is None or ps > best[0]:
                best = (ps, t)
        matrix.append(
            {
                "run_id": rid,
                "run_type": run.get("run_type") or run.get("_kind"),
                "tickets": tickets,
                "best_prize_level": best[1]["prize_level"] if best else "no_prize",
            }
        )
    return matrix


def prize_distribution_from_matrix(hit_matrix: list[dict[str, Any]]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for row in hit_matrix:
        for t in row.get("tickets", []):
            key = str(t.get("prize_level"))
            dist[key] = dist.get(key, 0) + 1
    return dist


def _recent_postmortem_scores(store: JsonStore, n: int = 6) -> list[float]:
    pm = store.read("postmortems.json", default={"items": []})
    items = list(pm.get("items", []))[-n:]
    scores: list[float] = []
    for it in items:
        if "postmortem_score" in it:
            scores.append(float(it["postmortem_score"]))
    return scores


def build_and_persist_postmortem(
    store: JsonStore,
    issue: str,
    *,
    model_version_hint: str | None = None,
) -> dict[str, Any]:
    draw = _find_draw_for_issue(store, issue)
    if not draw:
        raise ValueError(f"issue not found: {issue}")
    df = draw.get("front") or []
    db = draw.get("back") or []
    if len(df) != 5 or len(db) != 2:
        raise ValueError("draw result incomplete for postmortem")

    draw_key = {"front": sorted(df), "back": sorted(db)}
    pm_existing = store.read("postmortems.json", default={"items": []})
    for it in pm_existing.get("items", []):
        if str(it.get("issue")) != str(issue):
            continue
        dr = it.get("draw_result") or {}
        if dr.get("front") == draw_key["front"] and dr.get("back") == draw_key["back"]:
            agg = float(it.get("postmortem_score", 0))
            return {
                "postmortem_id": str(it.get("postmortem_id")),
                "score_summary": {
                    "postmortem_score": agg,
                    "prize_score": agg,
                    "structure_score": agg,
                    "stability_score": agg,
                },
                "triggered_actions": [],
                "idempotent": True,
            }

    runs = _collect_runs_for_issue(store, issue)
    if not runs:
        postmortem_id = f"pm_{issue}_{uuid.uuid4().hex[:10]}"
        item = {
            "postmortem_id": postmortem_id,
            "issue": issue,
            "model_version": model_version_hint or "unknown",
            "run_refs": [],
            "draw_result": {"front": sorted(df), "back": sorted(db)},
            "hit_matrix": [],
            "prize_distribution": {},
            "postmortem_score": 0.0,
            "prize_score": 0.0,
            "structure_score": 0.0,
            "stability_score": 0.0,
            "triggered_optimize": False,
            "created_at": utc_now_iso(),
        }
        payload = store.read("postmortems.json", default={"items": []})
        payload.setdefault("items", []).append(item)
        store.write("postmortems.json", payload)
        return {
            "postmortem_id": postmortem_id,
            "score_summary": {"postmortem_score": 0.0, "prize_score": 0.0, "structure_score": 0.0, "stability_score": 0.0},
            "triggered_actions": [],
        }

    hit_matrix = build_hit_matrix(draw, runs)
    dist = prize_distribution_from_matrix(hit_matrix)
    run_refs = [str(r.get("run_id")) for r in runs]

    best_prize = 0.0
    best_struct = 0.0
    for row in hit_matrix:
        for t in row.get("tickets", []):
            pl = t["prize_level"]
            best_prize = max(best_prize, prize_level_to_score(pl if pl != "no_prize" else "no_prize"))
            best_struct = max(best_struct, float(t.get("structure_score") or 0))

    recent = _recent_postmortem_scores(store, n=6)
    stab = stability_score_from_history(recent)
    agg = compute_postmortem_aggregate(best_prize, best_struct, stab)

    mv = model_version_hint or str(runs[0].get("model_version") or "unknown")

    postmortem_id = f"pm_{issue}_{uuid.uuid4().hex[:10]}"
    item = {
        "postmortem_id": postmortem_id,
        "issue": issue,
        "model_version": mv,
        "run_refs": run_refs,
        "draw_result": {"front": sorted(df), "back": sorted(db)},
        "hit_matrix": hit_matrix,
        "prize_distribution": dist,
        "postmortem_score": agg,
        "prize_score": best_prize,
        "structure_score": best_struct,
        "stability_score": stab,
        "triggered_optimize": False,
        "created_at": utc_now_iso(),
    }
    payload = store.read("postmortems.json", default={"items": []})
    payload.setdefault("items", []).append(item)
    store.write("postmortems.json", payload)

    # Update predictions with prize_summary / postmortem_status
    preds = store.read("predictions.json", default={"official": [], "experimental": []})
    for bucket in ("official", "experimental"):
        for row in preds.get(bucket, []):
            if str(row.get("target_issue")) != str(issue):
                continue
            rid = row.get("run_id")
            match = next((m for m in hit_matrix if m.get("run_id") == rid), None)
            if not match:
                continue
            best_level: Any = "no_prize"
            best_ps = 0.0
            for t in match.get("tickets", []):
                pl = t["prize_level"]
                ps = prize_level_to_score(pl if pl != "no_prize" else "no_prize")
                if ps > best_ps:
                    best_ps = ps
                    best_level = pl
            row["postmortem_status"] = "completed"
            row["prize_summary"] = {
                "best_prize_level": best_level,
                "best_prize_score": best_ps,
                "postmortem_id": postmortem_id,
            }
    store.write("predictions.json", preds)

    return {
        "postmortem_id": postmortem_id,
        "score_summary": {
            "postmortem_score": agg,
            "prize_score": best_prize,
            "structure_score": best_struct,
            "stability_score": stab,
        },
        "triggered_actions": [],
    }
