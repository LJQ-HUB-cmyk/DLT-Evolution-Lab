from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Callable

from app.engine.drift import N_REF_DEFAULT, compute_drift_report
from app.services.predict_pipeline import default_model_config
from app.engine.model_credit import (
    apply_drift_to_config,
    bump_consecutive_warn,
    decay_factor_for_level,
    merge_config_overrides,
    registry_status_from_credit,
    should_enqueue_optimize,
    update_credit_score,
)
from app.services.json_store import JsonStore


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_registry_item(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    if "credit_score" not in out and out.get("credit") is not None:
        try:
            out["credit_score"] = float(out["credit"]) * 70.0 if float(out["credit"]) <= 1.5 else float(out["credit"])
        except (TypeError, ValueError):
            out["credit_score"] = 70.0
    out.setdefault("credit_score", 70.0)
    out.setdefault("status", "candidate")
    out.setdefault("config_overrides", {})
    out.setdefault("consecutive_warn_count", 0)
    out.setdefault("promotion_evidence", None)
    out.setdefault("drift_profile_ref", None)
    out.setdefault("last_gate_result", None)
    out.setdefault("drift_summary", None)
    out.setdefault("notes", "")
    out.setdefault("created_at", _iso_now())
    out.setdefault("updated_at", _iso_now())
    return out


def normalize_registry(payload: dict[str, Any]) -> dict[str, Any]:
    items = [normalize_registry_item(x) for x in payload.get("items", [])]
    return {"items": items}


def get_champion_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for it in items:
        if it.get("status") == "champion":
            return it
    return items[0] if items else None


def merge_champion_config(store: JsonStore, default_cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    reg = normalize_registry(store.read("model_registry.json", default={"items": []}))
    items = reg.get("items", [])
    if not items:
        raise RuntimeError("MODEL_NOT_FOUND")
    champ = get_champion_item(items)
    if not champ:
        raise RuntimeError("MODEL_NOT_FOUND")
    ver = str(champ["version"])
    merged = merge_config_overrides(default_cfg, champ.get("config_overrides") or {})
    return ver, merged


def apply_feature_decay_to_structure(overrides: dict[str, Any], decay: float) -> dict[str, Any]:
    if decay >= 0.999:
        return overrides
    st = copy.deepcopy(overrides.get("structure") or {})
    for plan in ("plan1", "plan2"):
        sw = st.get(plan)
        if isinstance(sw, dict):
            for k in sw:
                sw[k] = round(float(sw[k]) * decay, 6)
    out = copy.deepcopy(overrides)
    out["structure"] = st
    return out


def apply_after_experimental(
    store: JsonStore,
    *,
    run: dict[str, Any],
    baseline: dict[str, Any] | None,
    history_slice: list[dict[str, Any]],
    reproducibility_alarm: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Update registry from drift report; return drift_report dict, model_credit dict, optimize_triggered."""
    reg = normalize_registry(store.read("model_registry.json", default={"items": []}))
    items = reg["items"]
    champ_idx = next((i for i, x in enumerate(items) if x.get("status") == "champion"), None)
    if champ_idx is None:
        champ_idx = 0
        if items:
            items[0]["status"] = "champion"
    champ = items[champ_idx]

    drift = compute_drift_report(
        run_id=str(run["run_id"]),
        target_issue=str(run["target_issue"]),
        model_version=str(run["model_version"]),
        snapshot_hash=str(run.get("snapshot_hash", "")),
        baseline=baseline,
        current=run,
        history_runs=history_slice,
    )
    ddict = drift.model_dump(mode="json")
    level = drift.drift_level
    prev_credit = float(champ.get("credit_score", 70.0))
    new_credit = update_credit_score(prev_credit, drift.drift_score, reproducibility_alarm=reproducibility_alarm)
    decay = decay_factor_for_level(level)
    co = copy.deepcopy(champ.get("config_overrides") or {})
    if decay < 1.0:
        co = apply_feature_decay_to_structure(co, decay)
    full_cfg = merge_config_overrides(default_model_config(), co)
    if level != "NORMAL":
        full_cfg = apply_drift_to_config(full_cfg, level)
    champ["config_overrides"] = {
        "structure": full_cfg.get("structure", {}),
        "search": full_cfg.get("search", {}),
    }
    cw = bump_consecutive_warn(level, int(champ.get("consecutive_warn_count", 0)))
    champ["consecutive_warn_count"] = cw
    champ["credit_score"] = new_credit
    champ["drift_summary"] = {
        "last_drift_score": drift.drift_score,
        "last_drift_level": drift.drift_level,
        "last_run_id": run["run_id"],
    }
    champ["drift_profile_ref"] = str(run.get("run_id"))
    prev_st = str(champ.get("status", "champion"))
    champ["status"] = registry_status_from_credit(new_credit, prev_st)
    champ["updated_at"] = _iso_now()

    opt_flag = should_enqueue_optimize(level, new_credit, cw)
    credit_info = {
        "model_version": champ["version"],
        "credit_score": new_credit,
        "status": champ["status"],
        "consecutive_warn_count": cw,
    }
    store.write("model_registry.json", {"items": items})
    store.append_log(
        "scheduler_logs.json",
        action="drift",
        result=level,
        detail=f"run_id={run['run_id']},score={drift.drift_score}",
        target_issue=str(run.get("target_issue")),
        snapshot_hash=str(run.get("snapshot_hash")),
        model_version=str(run.get("model_version")),
    )
    return ddict, credit_info, opt_flag


def append_candidate_model(
    store: JsonStore,
    *,
    base_version: str,
    optimization_run_id: str,
    config_overrides: dict[str, Any],
    best_score: float,
) -> str:
    reg = normalize_registry(store.read("model_registry.json", default={"items": []}))
    cand_ver = f"{base_version}-cand-{optimization_run_id[-8:]}"
    item = normalize_registry_item(
        {
            "version": cand_ver,
            "status": "candidate",
            "credit_score": 70.0,
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
            "notes": f"from_optimization {optimization_run_id}",
            "config_overrides": config_overrides,
            "promotion_evidence": {"optimization_run_id": optimization_run_id, "best_score": best_score},
        }
    )
    reg["items"].append(item)
    store.write("model_registry.json", reg)
    store.append_log(
        "scheduler_logs.json",
        action="candidate_register",
        result="ok",
        detail=f"version={cand_ver}",
        model_version=cand_ver,
    )
    return cand_ver


def evaluate_walk_forward_gate(
    *,
    champion_objective: float,
    candidate_objective: float,
    champion_fold_min: float,
    candidate_fold_min: float,
    drift_champion_mean: float,
    drift_candidate_mean: float,
    reproducibility_passes: int,
    reproducibility_total: int,
    predict_p95: float,
    degraded_test_data: bool,
) -> dict[str, Any]:
    if degraded_test_data:
        return {
            "passed": False,
            "degraded_test_data": True,
            "reason": "insufficient_or_degraded_test_data",
        }
    rel_improve = (candidate_objective - champion_objective) / max(abs(champion_objective), 1e-6)
    fold_ok = candidate_fold_min >= champion_fold_min - 0.02
    drift_ok = drift_candidate_mean <= drift_champion_mean + 0.05
    repro_ok = reproducibility_passes >= reproducibility_total
    perf_ok = predict_p95 < 3.0
    passed = rel_improve >= 0.03 and fold_ok and drift_ok and repro_ok and perf_ok
    return {
        "passed": passed,
        "degraded_test_data": False,
        "relative_improvement": round(rel_improve, 6),
        "fold_ok": fold_ok,
        "drift_ok": drift_ok,
        "repro_ok": repro_ok,
        "perf_ok": perf_ok,
    }


def _write_registry_items_preserve_extras(store: JsonStore, items: list[dict[str, Any]]) -> None:
    payload = store.read("model_registry.json", default={"items": []})
    payload["items"] = items
    store.write("model_registry.json", payload)


def try_promote_candidate(
    store: JsonStore,
    candidate_version: str,
    gate_result: dict[str, Any] | None = None,
    gate_builder: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reg = normalize_registry(store.read("model_registry.json", default={"items": []}))
    items = reg["items"]
    cand = next((x for x in items if x.get("version") == candidate_version), None)
    if not cand:
        return {"ok": False, "reason": "candidate_not_found"}
    gr = gate_result if gate_result is not None else (gate_builder() if gate_builder else {"passed": False})
    cand["last_gate_result"] = gr
    cand["updated_at"] = _iso_now()
    if not gr.get("passed") or gr.get("degraded_test_data"):
        _write_registry_items_preserve_extras(store, items)
        return {"ok": False, "reason": gr.get("reason", "gate_failed"), "gate_result": gr}
    for it in items:
        if it.get("status") == "champion":
            it["status"] = "deprecated"
            it["updated_at"] = _iso_now()
    cand["status"] = "champion"
    cand["promotion_evidence"] = {**(cand.get("promotion_evidence") or {}), "gate_result": gr}
    cand["updated_at"] = _iso_now()
    _write_registry_items_preserve_extras(store, items)
    store.append_log(
        "scheduler_logs.json",
        action="promote",
        result="ok",
        detail=f"candidate={candidate_version}",
        model_version=candidate_version,
    )
    return {"ok": True, "gate_result": gr}


def recent_experimental_for_target(
    predictions_payload: dict[str, Any],
    target_issue: str,
    limit: int = N_REF_DEFAULT,
) -> list[dict[str, Any]]:
    exp = predictions_payload.get("experimental") or []
    same = [x for x in exp if str(x.get("target_issue")) == str(target_issue)]
    return same[-limit:]


def find_official_baseline(predictions_payload: dict[str, Any], target_issue: str) -> dict[str, Any] | None:
    for o in predictions_payload.get("official") or []:
        if str(o.get("target_issue")) == str(target_issue):
            return o
    return None


def _append_promotion_m5_log(store: JsonStore, evidence: dict[str, Any]) -> None:
    payload = store.read("model_registry.json", default={"items": []})
    payload.setdefault("promotion_logs", []).append(evidence)
    payload["promotion_logs"] = payload["promotion_logs"][-100:]
    store.write("model_registry.json", payload)


def _credit_metric_for_m5(item: dict[str, Any]) -> float:
    c = item.get("credit")
    if c is not None:
        try:
            return float(c)
        except (TypeError, ValueError):
            pass
    return float(item.get("credit_score", 0.0))


def evaluate_promotion_after_optimize(
    store: JsonStore,
    *,
    backtest_gate_ok: bool | None = None,
    stability_ok: bool | None = None,
) -> dict[str, Any]:
    """M5: 优化成功后评估候选晋升；仅门禁与信用优势通过时晋升冠军。"""
    evidence: dict[str, Any] = {
        "evaluated_at": _iso_now(),
        "promoted": False,
        "reason": "",
    }
    opt = store.read("optimization_runs.json", default={"items": []})
    items_opt = opt.get("items", [])
    last_opt = items_opt[-1] if items_opt else None

    reg = normalize_registry(store.read("model_registry.json", default={"items": []}))
    mitems = reg.get("items", [])
    champion = get_champion_item(mitems)
    candidates = [x for x in mitems if x.get("status") == "candidate"]

    opt_ok = last_opt and last_opt.get("status") in ("succeeded", "completed")
    if not opt_ok:
        evidence["reason"] = "no_succeeded_optimize"
        _append_promotion_m5_log(store, evidence)
        return evidence
    if not candidates:
        evidence["reason"] = "no_candidate"
        _append_promotion_m5_log(store, evidence)
        return evidence
    if champion is None:
        evidence["reason"] = "no_champion"
        _append_promotion_m5_log(store, evidence)
        return evidence

    gate_bt = True if backtest_gate_ok is None else bool(backtest_gate_ok)
    gate_st = True if stability_ok is None else bool(stability_ok)
    if not gate_bt or not gate_st:
        evidence["reason"] = "gates_failed"
        evidence["backtest_gate_ok"] = gate_bt
        evidence["stability_ok"] = gate_st
        _append_promotion_m5_log(store, evidence)
        return evidence

    best = max(candidates, key=_credit_metric_for_m5)
    ch_m = _credit_metric_for_m5(champion)
    ca_m = _credit_metric_for_m5(best)
    if ca_m <= ch_m * 1.001:
        evidence["reason"] = "insufficient_credit_delta"
        _append_promotion_m5_log(store, evidence)
        return evidence

    gate_result = {
        "passed": True,
        "degraded_test_data": False,
        "m5_backtest_gate": gate_bt,
        "m5_stability_gate": gate_st,
    }
    pr = try_promote_candidate(store, str(best["version"]), gate_result=gate_result)
    evidence["promoted"] = bool(pr.get("ok"))
    evidence["from_version"] = champion.get("version")
    evidence["to_version"] = best.get("version")
    evidence["reason"] = "promoted" if evidence["promoted"] else str(pr.get("reason", "promote_failed"))
    evidence["gate_result"] = pr.get("gate_result")
    _append_promotion_m5_log(store, evidence)
    return evidence
