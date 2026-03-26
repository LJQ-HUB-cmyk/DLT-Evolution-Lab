from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from app.engine.optimize import (
    canonical_search_space_hash,
    params_to_model_config_patch,
    run_optuna_study,
    search_space_hash,
)
from app.services.json_store import JsonStore
from app.services.model_registry_service import append_candidate_model, get_champion_item, normalize_registry

OptimizeTriggerSource = Literal["manual", "auto_drift", "auto_credit"]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def should_trigger_optimize(
    store: JsonStore,
    *,
    score_threshold: float = 55.0,
) -> tuple[bool, list[str]]:
    """M5 §7.1 + M4 信用/漂移：任一条成立则触发优化。"""
    reasons: list[str] = []

    items = store.read("postmortems.json", default={"items": []}).get("items", [])
    last6 = items[-6:]
    if len(last6) >= 3:
        scores = [float(x.get("postmortem_score", 0)) for x in last6]
        if scores and sum(scores) / len(scores) < score_threshold:
            reasons.append("rolling_mean_postmortem_score_low")

    def _issue_had_any_prize(pm_item: dict[str, Any]) -> bool:
        for row in pm_item.get("hit_matrix") or []:
            for t in row.get("tickets", []):
                pl = t.get("prize_level")
                if pl not in (None, "no_prize"):
                    return True
        return False

    consecutive_no_prize = 0
    for it in reversed(items):
        if _issue_had_any_prize(it):
            break
        consecutive_no_prize += 1
    if consecutive_no_prize >= 3:
        reasons.append("consecutive_no_prize_hits")

    preds = store.read("predictions.json", default={"official": [], "experimental": []})
    for run in (preds.get("experimental") or [])[-30:]:
        d = run.get("drift") or {}
        if d.get("unstable"):
            reasons.append("drift_warn_or_critical")
            break
        lvl = str(d.get("level") or d.get("drift_level") or "").upper()
        if lvl in {"WARN", "CRITICAL"}:
            reasons.append("drift_warn_or_critical")
            break
        try:
            if float(d.get("drift_score", 0)) >= 0.75:
                reasons.append("drift_warn_or_critical")
                break
        except (TypeError, ValueError):
            pass

    reg = normalize_registry(store.read("model_registry.json", default={"items": []}))
    champ = get_champion_item(reg.get("items", []))
    if champ:
        credit = float(champ.get("credit_score", 70.0))
        if credit < 55.0:
            reasons.append("credit_below_55")
        if int(champ.get("consecutive_warn_count", 0)) >= 3:
            reasons.append("consecutive_warn")

    # dedupe
    reasons = list(dict.fromkeys(reasons))
    return (len(reasons) > 0), reasons


def mark_last_optimization_succeeded(store: JsonStore, gate_passed: bool = True) -> None:
    payload = store.read("optimization_runs.json", default={"items": []})
    items = payload.get("items", [])
    if not items:
        return
    items[-1]["optimization_succeeded"] = True
    items[-1]["promotion_precheck_passed"] = bool(gate_passed)
    store.write("optimization_runs.json", payload)


def queue_optimization_run(
    store: JsonStore,
    *,
    reason: str = "",
    triggered_by: str = "postmortem",
) -> dict[str, Any]:
    reg = normalize_registry(store.read("model_registry.json", default={"items": []}))
    champ = get_champion_item(reg.get("items", []))
    base = str(champ["version"]) if champ else "unknown"
    out = enqueue_optimize(
        store,
        trigger_source="manual",
        base_model_version=base,
        budget_trials=80,
        time_limit_minutes=45,
        execute=True,
    )
    rid = out.get("optimization_run_id")
    return {**out, "run_id": rid, "reason": reason, "triggered_by": triggered_by}


def enqueue_optimize(
    store: JsonStore,
    *,
    trigger_source: OptimizeTriggerSource,
    base_model_version: str,
    budget_trials: int = 80,
    time_limit_minutes: int = 45,
    execute: bool = True,
    objective_probe: Any = None,
) -> dict[str, Any]:
    payload = store.read("optimization_runs.json", default={"items": []})
    run_id = f"opt_{uuid.uuid4().hex[:12]}"
    queued_at = _iso_now()
    item: dict[str, Any] = {
        "run_id": run_id,
        "trigger_source": trigger_source,
        "base_model_version": base_model_version,
        "search_space_hash": "",
        "study_summary": {},
        "best_params": {},
        "best_score": None,
        "gate_result": {},
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "queued_at": queued_at,
        "failed_reason": None,
        "budget_trials": budget_trials,
        "time_limit_minutes": time_limit_minutes,
    }
    payload.setdefault("items", []).append(item)
    store.write("optimization_runs.json", payload)
    store.append_log(
        "scheduler_logs.json",
        action="optimize",
        result="queued",
        detail=f"run_id={run_id},trigger={trigger_source}",
        model_version=base_model_version,
    )
    if execute:
        return execute_optimization_run(store, run_id, objective_probe=objective_probe)
    return {
        "optimization_run_id": run_id,
        "status": "queued",
        "queued_at": queued_at,
    }


def execute_optimization_run(
    store: JsonStore,
    run_id: str,
    *,
    objective_probe: Any = None,
) -> dict[str, Any]:
    payload = store.read("optimization_runs.json", default={"items": []})
    items = payload.get("items", [])
    target = next((x for x in items if x.get("run_id") == run_id), None)
    if not target:
        raise KeyError(run_id)
    target["status"] = "running"
    target["started_at"] = _iso_now()
    store.write("optimization_runs.json", payload)
    try:
        ssh = canonical_search_space_hash()
        best_params, best_score, meta = run_optuna_study(
            run_id=run_id,
            n_trials=int(target.get("budget_trials", 80)),
            time_limit_minutes=float(target.get("time_limit_minutes", 45)),
            objective_probe=objective_probe,
            seed=42,
        )
        target["search_space_hash"] = ssh
        target["best_params"] = best_params
        target["trial_params_hash"] = search_space_hash(best_params)
        target["best_score"] = best_score
        target["study_summary"] = meta.get("study_summary", {})
        target["status"] = "completed"
        target["finished_at"] = _iso_now()
        target["failed_reason"] = None
        patch = params_to_model_config_patch(best_params)
        cand_ver = append_candidate_model(
            store,
            base_version=str(target.get("base_model_version", "unknown")),
            optimization_run_id=run_id,
            config_overrides=patch,
            best_score=best_score,
        )
        target["gate_result"] = {"candidate_version": cand_ver, "registered": True}
        store.write("optimization_runs.json", payload)
        store.append_log(
            "scheduler_logs.json",
            action="optimize",
            result="completed",
            detail=f"run_id={run_id},score={best_score}",
            model_version=str(target.get("base_model_version")),
        )
    except Exception as e:
        target["status"] = "failed"
        target["finished_at"] = _iso_now()
        target["failed_reason"] = str(e)
        store.write("optimization_runs.json", payload)
        store.append_log(
            "scheduler_logs.json",
            action="optimize",
            result="failed",
            detail=f"run_id={run_id},err={e!s}",
        )
        return {
            "optimization_run_id": run_id,
            "status": "failed",
            "queued_at": target.get("queued_at"),
            "failed_reason": str(e),
        }
    return {
        "optimization_run_id": run_id,
        "status": target["status"],
        "queued_at": target.get("queued_at"),
        "best_score": target.get("best_score"),
    }
