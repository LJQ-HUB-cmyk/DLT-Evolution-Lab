from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.automation_pipeline import run_sync_job
from app.services.sporttery_history_service import sync_sporttery_history
from app.services.json_store import JsonStore
from app.services.model_registry_service import (
    apply_after_experimental,
    find_official_baseline,
    merge_champion_config,
    normalize_registry_item,
    recent_experimental_for_target,
)
from app.services.optimization_service import (
    enqueue_optimize,
    queue_optimization_run,
    should_trigger_optimize,
)
from app.services.postmortem_service import build_and_persist_postmortem
from app.services.predict_pipeline import (
    PipelineError,
    build_analysis_payload,
    default_model_config,
    run_prediction,
)

router = APIRouter(prefix="/api", tags=["dlt"])
store = JsonStore()


class OptimizeBody(BaseModel):
    trigger_source: Literal["manual", "auto_drift", "auto_credit"] = "manual"
    base_model_version: str = ""
    budget_trials: int = Field(default=80, ge=1, le=500)
    time_limit_minutes: int = Field(default=45, ge=1, le=180)


def _champion_config() -> tuple[str, dict]:
    try:
        return merge_champion_config(store, default_model_config())
    except RuntimeError as e:
        if str(e) == "MODEL_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={"error_code": "MODEL_NOT_FOUND", "message": "empty registry"},
            ) from e
        raise


@router.get("/issues")
def get_issues() -> dict:
    return store.read("issues.json", default={"items": []})


@router.post("/sync")
def sync_data(
    trigger_source: Literal["schedule", "manual", "retry", "chained"] = "manual",
    history_limit: int = Query(default=500, ge=1, le=3000, description="Pull and keep latest N issues"),
) -> dict:
    task = run_sync_job(store, trigger_source=trigger_source, history_limit=history_limit)
    detail = task.get("detail") or {}
    sync_body = detail.get("sync")
    if sync_body is None and task.get("status") == "skipped":
        issues = store.read("issues.json", default={"items": []})
        sync_body = {
            "ok": True,
            "degraded": False,
            "mode": "skipped",
            "issueCount": len(issues.get("items", [])),
            "warnings": [],
            "snapshots": {},
        }
    if sync_body is None:
        sync_body = {
            "ok": False,
            "degraded": True,
            "warnings": ["sync task did not return payload"],
            "issueCount": 0,
        }
    return {
        **sync_body,
        "scheduler_context": {
            "trigger_source": trigger_source,
            "task_status": task.get("status"),
            "task_id": task.get("task_id"),
            "idempotency_key": task.get("idempotency_key"),
        },
    }


@router.post("/sync/history")
def sync_history(
    limit: int = Query(default=500, ge=1, le=3000, description="Keep this many latest issues after merge"),
    page_size: int = Query(default=30, ge=10, le=100, description="Sporttery API page size"),
) -> dict:
    """Fetch recent DLT draws from sporttery.cn gateway (gameNo=85), merge, trim to ``limit``."""
    return sync_sporttery_history(limit=limit, page_size=page_size)


@router.get("/issues/status")
def get_issue_status() -> dict:
    issues_payload = store.read("issues.json", default={"items": []})
    models_payload = store.read("model_registry.json", default={"items": []})
    logs_payload = store.read("scheduler_logs.json", default={"logs": []})
    postmortems_payload = store.read("postmortems.json", default={"items": []})
    optimization_payload = store.read("optimization_runs.json", default={"items": []})
    latest_sync = None
    for item in reversed(logs_payload.get("logs", [])):
        if item.get("action") == "sync":
            latest_sync = item.get("timestamp")
            break
    logs = logs_payload.get("logs", [])
    post_items = postmortems_payload.get("items", [])
    opt_items = optimization_payload.get("items", [])
    return {
        "issueCount": len(issues_payload.get("items", [])),
        "modelCount": len(models_payload.get("items", [])),
        "latestSyncAt": latest_sync,
        "latestIssue": issues_payload.get("items", [{}])[0].get("issue") if issues_payload.get("items") else None,
        "logCount": len(logs),
        "schedulerLogs": logs[-80:],
        "postmortems": post_items[-40:],
        "optimizationRuns": opt_items[-40:],
    }


@router.get("/analysis/{target_issue}")
def get_analysis(target_issue: str) -> dict:
    try:
        mv, cfg = _champion_config()
        return build_analysis_payload(target_issue, mv, cfg)
    except PipelineError as e:
        if e.code == "INSUFFICIENT_HISTORY":
            raise HTTPException(
                status_code=422,
                detail={"error_code": e.code, "message": e.message},
            ) from e
        raise HTTPException(
            status_code=500,
            detail={"error_code": "PIPELINE_FAILED", "message": e.message},
        ) from e


@router.post("/publish/{target_issue}")
def publish(target_issue: str, seed: int = 20260326) -> dict:
    payload = store.read("predictions.json", default={"official": [], "experimental": []})
    for item in payload.get("official", []):
        if item.get("target_issue") == target_issue:
            return {"ok": True, "officialPrediction": item, "idempotent": True}

    try:
        mv, cfg = _champion_config()
        result = run_prediction(
            target_issue=target_issue,
            mode="official",
            seed=seed,
            model_version=mv,
            model_config=cfg,
        )
    except PipelineError as e:
        if e.code == "INSUFFICIENT_HISTORY":
            raise HTTPException(
                status_code=422,
                detail={"error_code": e.code, "message": e.message},
            ) from e
        if e.code == "MODEL_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={"error_code": e.code, "message": e.message},
            ) from e
        raise HTTPException(
            status_code=500,
            detail={"error_code": "PIPELINE_FAILED", "message": e.message},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error_code": "PIPELINE_FAILED", "message": str(e)},
        ) from e

    official = result["officialPrediction"]
    payload["official"].append(official)
    store.write("predictions.json", payload)
    store.append_log(
        "scheduler_logs.json",
        action="publish",
        result="ok",
        detail=f"run_id={official.get('run_id')}",
        target_issue=target_issue,
        snapshot_hash=official.get("snapshot_hash"),
        model_version=official.get("model_version"),
        duration_ms=result.get("_duration_ms"),
    )
    return {"ok": True, "officialPrediction": official}


@router.post("/predict/{target_issue}")
def predict(target_issue: str, seed: int = 20260326) -> dict:
    try:
        mv, cfg = _champion_config()
        pred_before = store.read("predictions.json", default={"official": [], "experimental": []})
        baseline = find_official_baseline(pred_before, target_issue)
        hist = recent_experimental_for_target(pred_before, target_issue)
        result = run_prediction(
            target_issue=target_issue,
            mode="experimental",
            seed=seed,
            model_version=mv,
            model_config=cfg,
        )
    except PipelineError as e:
        if e.code == "INSUFFICIENT_HISTORY":
            raise HTTPException(
                status_code=422,
                detail={"error_code": e.code, "message": e.message},
            ) from e
        if e.code == "MODEL_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={"error_code": e.code, "message": e.message},
            ) from e
        raise HTTPException(
            status_code=500,
            detail={"error_code": "PIPELINE_FAILED", "message": e.message},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error_code": "PIPELINE_FAILED", "message": str(e)},
        ) from e

    run = result["run"]
    drift_report, model_credit, optimize_triggered = apply_after_experimental(
        store,
        run=run,
        baseline=baseline,
        history_slice=hist,
    )
    run["drift"] = drift_report
    payload = store.read("predictions.json", default={"official": [], "experimental": []})
    payload["experimental"].append(run)
    store.write("predictions.json", payload)
    store.append_log(
        "scheduler_logs.json",
        action="predict",
        result="ok",
        detail=f"run_id={run.get('run_id')}",
        target_issue=target_issue,
        snapshot_hash=run.get("snapshot_hash"),
        model_version=run.get("model_version"),
        duration_ms=result.get("_duration_ms"),
    )
    if optimize_triggered:
        reg = store.read("model_registry.json", default={"items": []})
        champ = next((x for x in reg.get("items", []) if x.get("status") == "champion"), None)
        bv = str((champ or {}).get("version") or mv)
        enqueue_optimize(
            store,
            trigger_source="auto_drift",
            base_model_version=bv,
            budget_trials=80,
            time_limit_minutes=45,
            execute=True,
        )
        store.append_log(
            "scheduler_logs.json",
            action="optimize",
            result="auto_enqueued",
            detail=f"after_drift run_id={run.get('run_id')}",
            model_version=bv,
        )
    return {
        "ok": True,
        "run": run,
        "drift_report": drift_report,
        "model_credit": model_credit,
        "optimize_triggered": optimize_triggered,
    }


@router.post("/anchor/recompute")
def recompute_anchor() -> dict:
    try:
        mv, cfg = _champion_config()
        result = run_prediction(
            target_issue="next",
            mode="experimental",
            seed=4242,
            model_version=mv,
            model_config=cfg,
        )
    except PipelineError as e:
        if e.code == "INSUFFICIENT_HISTORY":
            raise HTTPException(
                status_code=422,
                detail={"error_code": e.code, "message": e.message},
            ) from e
        raise HTTPException(
            status_code=500,
            detail={"error_code": "PIPELINE_FAILED", "message": e.message},
        ) from e

    run = result["run"]
    p1 = run.get("plan1") or []
    if not p1:
        raise HTTPException(status_code=500, detail={"error_code": "PIPELINE_FAILED", "message": "empty plan1"})
    t0 = p1[0]
    anchor_payload = {
        "model_version": mv,
        "target_issue": run.get("target_issue", "next"),
        "ticket": t0,
        "locked": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    store.write("anchor_ticket.json", anchor_payload)
    store.append_log(
        "scheduler_logs.json",
        action="anchor_recompute",
        result="ok",
        target_issue=anchor_payload["target_issue"],
        snapshot_hash=run.get("snapshot_hash"),
        model_version=mv,
        duration_ms=result.get("_duration_ms"),
    )
    return {"ok": True, "anchor": anchor_payload}


@router.post("/postmortem/{issue}")
def postmortem(issue: str) -> dict:
    try:
        out = build_and_persist_postmortem(store, issue)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if out.get("idempotent"):
        return {
            "postmortem_id": out["postmortem_id"],
            "score_summary": out["score_summary"],
            "triggered_actions": [],
        }

    triggered: list[str] = []
    should_opt, reasons = should_trigger_optimize(store)
    if should_opt:
        queue_optimization_run(store, reason=",".join(reasons), triggered_by="api_postmortem")
        triggered.append("optimize_job")
        pm = store.read("postmortems.json", default={"items": []})
        pid = out.get("postmortem_id")
        for it in pm.get("items", []):
            if it.get("postmortem_id") == pid:
                it["triggered_optimize"] = True
        store.write("postmortems.json", pm)

    store.append_log(
        "scheduler_logs.json",
        action="postmortem",
        result="ok",
        detail=f"postmortem_id={out.get('postmortem_id')}",
        target_issue=issue,
    )
    return {
        "postmortem_id": out["postmortem_id"],
        "score_summary": out["score_summary"],
        "triggered_actions": triggered,
    }


@router.post("/optimize")
def optimize(body: OptimizeBody | None = None) -> dict:
    b = body or OptimizeBody()
    mv, _ = _champion_config()
    base = b.base_model_version or mv
    out = enqueue_optimize(
        store,
        trigger_source=b.trigger_source,
        base_model_version=base,
        budget_trials=b.budget_trials,
        time_limit_minutes=b.time_limit_minutes,
        execute=True,
    )
    return {
        "ok": out.get("status") != "failed",
        "optimization_run_id": out.get("optimization_run_id"),
        "status": out.get("status"),
        "queued_at": out.get("queued_at"),
        "best_score": out.get("best_score"),
        "failed_reason": out.get("failed_reason"),
    }


@router.get("/models")
def get_models() -> dict:
    raw = store.read("model_registry.json", default={"items": []})
    items = [normalize_registry_item(x) for x in raw.get("items", [])]
    for it in items:
        it.setdefault("drift_summary", it.get("drift_summary"))
        it.setdefault("last_gate_result", it.get("last_gate_result"))
    return {"items": items}


@router.get("/runs")
def get_runs(limit: int = 50) -> dict:
    payload = store.read("predictions.json", default={"official": [], "experimental": []})
    experiments = payload.get("experimental", [])[-limit:]
    enriched = []
    for run in experiments:
        row = dict(run)
        ps = row.get("prize_summary") or {}
        row["postmortem_ref"] = ps.get("postmortem_id")
        row["prize_summary"] = ps
        enriched.append(row)
    return {"items": enriched, "limit": limit}
