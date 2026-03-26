from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.services.json_store import JsonStore
from app.services.model_registry_service import evaluate_promotion_after_optimize
from app.services.official_sync_service import ingest_official_draw, sync_official_sources
from app.services.optimization_service import mark_last_optimization_succeeded, queue_optimization_run, should_trigger_optimize
from app.services.postmortem_service import build_and_persist_postmortem
from app.services.predict_pipeline import default_model_config, run_prediction
from app.services.scheduler_audit_service import append_alert, append_audit_entry, build_audit_entry, record_sync_failure_for_alerts, transition_task


def _champion_model_version(store: JsonStore) -> str:
    reg = store.read("model_registry.json", default={"items": []})
    for it in reg.get("items", []):
        if it.get("status") == "champion":
            return str(it["version"])
    items = reg.get("items", [])
    if items:
        return str(items[0]["version"])
    raise ValueError("MODEL_NOT_FOUND")


def _numeric_issue(issue: Any) -> int:
    try:
        return int(str(issue))
    except (TypeError, ValueError):
        return -1


def resolve_next_target_issue(store: JsonStore) -> str:
    issues_payload = store.read("issues.json", default={"items": []})
    items = list(issues_payload.get("items") or [])
    if not items:
        raise ValueError("TARGET_ISSUE_RESOLUTION_FAILED")
    latest_issue = str(max(items, key=lambda x: _numeric_issue(x.get("issue"))).get("issue", ""))
    if not latest_issue:
        raise ValueError("TARGET_ISSUE_RESOLUTION_FAILED")
    width = max(5, len(latest_issue))
    return f"{_numeric_issue(latest_issue) + 1:0{width}d}"


def _latest_open_prediction_issue(store: JsonStore) -> str | None:
    preds = store.read("predictions.json", default={"official": [], "experimental": []})
    postmortems = store.read("postmortems.json", default={"items": []})
    done = {str(x.get("issue")) for x in postmortems.get("items", []) if x.get("issue") is not None}
    candidates: set[str] = set()
    for row in preds.get("official", []):
        issue = str(row.get("target_issue") or "")
        if issue and issue not in done:
            candidates.add(issue)
    for row in preds.get("experimental", []):
        issue = str(row.get("target_issue") or "")
        if issue and issue not in done:
            candidates.add(issue)
    if not candidates:
        return None
    return max(candidates, key=_numeric_issue)


def run_sync_job(
    store: JsonStore,
    *,
    trigger_source: Literal["schedule", "manual", "retry", "chained"] = "schedule",
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        summary = sync_official_sources()
        warnings = list(summary.get("warnings") or [])
        ok = bool(summary.get("ok"))
        record_sync_failure_for_alerts(store, ok)
        return {
            "result_summary": f"sync ok={ok} issues={summary.get('issueCount')}",
            "warnings": warnings,
            "snapshot_hash": str((summary.get("snapshots") or {}).get("draw", {}).get("sha256") or ""),
            "model_version": "na",
            "sync": {
                "ok": ok,
                "degraded": summary.get("degraded"),
                "mode": summary.get("mode"),
                "syncedAt": summary.get("syncedAt"),
                "issueCount": summary.get("issueCount"),
                "newIssueCount": summary.get("newIssueCount"),
                "ruleVersionCount": summary.get("ruleVersionCount"),
                "warnings": warnings,
                "snapshots": summary.get("snapshots"),
            },
        }

    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return transition_task(
        store,
        task_type="sync_job",
        trigger_source=trigger_source,
        target_issue="",
        snapshot_hash="",
        model_version="na",
        date_bucket=bucket,
        runner=_run,
    )


def run_publish_check_job(
    store: JsonStore,
    *,
    target_issue: str = "",
    trigger_source: Literal["schedule", "manual", "retry", "chained"] = "schedule",
    seed: int = 20260326,
) -> dict[str, Any]:
    if not target_issue:
        target_issue = resolve_next_target_issue(store)
    preds = store.read("predictions.json", default={"official": [], "experimental": []})
    for o in preds.get("official", []):
        if str(o.get("target_issue")) == str(target_issue):
            return {
                "status": "skipped",
                "reason": "already_published",
                "officialPrediction": o,
            }

    mv = _champion_model_version(store)
    cfg = default_model_config()

    def _run() -> dict[str, Any]:
        result = run_prediction(
            target_issue=target_issue,
            mode="official",
            seed=seed,
            model_version=mv,
            model_config=cfg,
        )
        official = result["officialPrediction"]
        preds2 = store.read("predictions.json", default={"official": [], "experimental": []})
        preds2.setdefault("official", []).append(official)
        store.write("predictions.json", preds2)
        return {
            "result_summary": f"published run_id={official.get('run_id')}",
            "snapshot_hash": str(official.get("snapshot_hash") or ""),
            "model_version": str(official.get("model_version") or mv),
        }

    bucket = str(target_issue)
    sh = ""
    return transition_task(
        store,
        task_type="publish_check_job",
        trigger_source=trigger_source,
        target_issue=str(target_issue),
        snapshot_hash=sh,
        model_version=mv,
        date_bucket=bucket,
        runner=_run,
    )


def run_draw_poll_and_chain(
    store: JsonStore,
    *,
    target_issue: str,
    front: list[int],
    back: list[int],
    draw_date: str | None = None,
    trigger_source: Literal["schedule", "manual", "retry", "chained"] = "schedule",
) -> dict[str, Any]:
    """回填开奖并链式触发复盘 -> 优化 -> 晋升评估。"""

    def _ingest() -> dict[str, Any]:
        ing = ingest_official_draw(target_issue, front, back, draw_date=draw_date)
        if ing.get("status") == "data_conflict":
            raise RuntimeError("data_conflict: manual confirmation required")
        return {
            "result_summary": f"ingest {ing.get('status')}",
            "warnings": [],
            "snapshot_hash": "",
            "model_version": _champion_model_version(store),
        }

    bucket = str(target_issue)
    mv = _champion_model_version(store)
    r1 = transition_task(
        store,
        task_type="draw_ingest_job",
        trigger_source=trigger_source,
        target_issue=str(target_issue),
        snapshot_hash="",
        model_version=mv,
        date_bucket=bucket,
        runner=_ingest,
    )
    if r1.get("status") != "succeeded":
        return {"ingest": r1, "postmortem": None, "optimize": None, "promotion": None}

    pm = run_postmortem_job(store, issue=str(target_issue), trigger_source="chained")
    trig = False
    reasons: list[str] = []
    if pm.get("status") == "succeeded":
        should, reasons = should_trigger_optimize(store)
        trig = should
        pmr = pm.get("detail") or {}
        pid = pmr.get("postmortem_id")
        if pid:
            pitems = store.read("postmortems.json", default={"items": []})
            for it in pitems.get("items", []):
                if it.get("postmortem_id") == pid:
                    it["triggered_optimize"] = trig
            store.write("postmortems.json", pitems)

    opt_result = None
    prom: dict[str, Any] | None = None
    if trig:
        run = queue_optimization_run(store, reason=",".join(reasons), triggered_by="postmortem_pipeline")
        mark_last_optimization_succeeded(store, gate_passed=True)
        opt_result = run
        prom = evaluate_promotion_after_optimize(store)
    else:
        prom = {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "promoted": False,
            "reason": "optimize_not_triggered",
        }

    return {"ingest": r1, "postmortem": pm, "optimize": opt_result, "promotion": prom, "optimize_reasons": reasons}


def run_draw_poll_job(
    store: JsonStore,
    *,
    target_issue: str = "",
    trigger_source: Literal["schedule", "manual", "retry", "chained"] = "schedule",
) -> dict[str, Any]:
    sync_result = run_sync_job(store, trigger_source="chained")
    if sync_result.get("status") == "failed":
        return {
            "status": "failed",
            "reason": "sync_failed",
            "sync": sync_result,
        }

    resolved_issue = target_issue or _latest_open_prediction_issue(store)
    if not resolved_issue:
        return {
            "status": "skipped",
            "reason": "no_open_prediction_issue",
            "sync": sync_result,
        }

    issues_payload = store.read("issues.json", default={"items": []})
    row = None
    for it in issues_payload.get("items", []):
        if str(it.get("issue")) == str(resolved_issue):
            row = it
            break
    if row is None:
        return {
            "status": "skipped",
            "reason": "issue_not_in_synced_data",
            "target_issue": resolved_issue,
            "sync": sync_result,
        }

    front = sorted(int(x) for x in (row.get("front") or []))
    back = sorted(int(x) for x in (row.get("back") or []))
    if len(front) != 5 or len(back) != 2:
        return {
            "status": "skipped",
            "reason": "draw_not_available",
            "target_issue": resolved_issue,
            "sync": sync_result,
        }

    chained = run_draw_poll_and_chain(
        store,
        target_issue=str(resolved_issue),
        front=front,
        back=back,
        draw_date=row.get("draw_date"),
        trigger_source=trigger_source,
    )
    return {
        "status": "succeeded",
        "target_issue": str(resolved_issue),
        "sync": sync_result,
        **chained,
    }


def run_postmortem_job(
    store: JsonStore,
    *,
    issue: str,
    trigger_source: Literal["schedule", "manual", "retry", "chained"] = "manual",
) -> dict[str, Any]:
    mv = _champion_model_version(store)

    def _run() -> dict[str, Any]:
        out = build_and_persist_postmortem(store, issue, model_version_hint=mv)
        return {
            "result_summary": f"postmortem_id={out.get('postmortem_id')}",
            "warnings": [],
            "snapshot_hash": "",
            "model_version": mv,
            "detail": out,
        }

    bucket = str(issue)
    return transition_task(
        store,
        task_type="postmortem_job",
        trigger_source=trigger_source,
        target_issue=str(issue),
        snapshot_hash="",
        model_version=mv,
        date_bucket=bucket,
        runner=_run,
    )


def run_optimize_job(
    store: JsonStore,
    *,
    trigger_source: Literal["schedule", "manual", "retry", "chained"] = "manual",
    reason: str = "manual",
) -> dict[str, Any]:
    mv = _champion_model_version(store)

    def _run() -> dict[str, Any]:
        run = queue_optimization_run(store, reason=reason, triggered_by=trigger_source)
        return {
            "result_summary": run["run_id"],
            "snapshot_hash": "",
            "model_version": mv,
        }

    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    return transition_task(
        store,
        task_type="optimize_job",
        trigger_source=trigger_source,
        target_issue="",
        snapshot_hash="",
        model_version=mv,
        date_bucket=bucket,
        runner=_run,
    )


def run_promotion_eval_job(
    store: JsonStore,
    *,
    trigger_source: Literal["schedule", "manual", "retry", "chained"] = "chained",
) -> dict[str, Any]:
    mv = _champion_model_version(store)

    def _run() -> dict[str, Any]:
        ev = evaluate_promotion_after_optimize(store)
        return {
            "result_summary": str(ev.get("reason") or ev.get("promoted")),
            "snapshot_hash": "",
            "model_version": mv,
            "detail": ev,
        }

    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    return transition_task(
        store,
        task_type="promotion_eval_job",
        trigger_source=trigger_source,
        target_issue="",
        snapshot_hash="",
        model_version=mv,
        date_bucket=bucket,
        runner=_run,
    )


def log_draw_poll_timeout(store: JsonStore, target_issue: str) -> None:
    append_alert(store, "ALERT_DRAW_TIMEOUT", f"draw_poll_job >90m no result for issue={target_issue}")


def log_postmortem_failed_alert(store: JsonStore, message: str) -> None:
    append_audit_entry(
        store,
        build_audit_entry(
            task_id="alert",
            task_type="alert",
            trigger_source="schedule",
            status="failed",
            idempotency_key="na",
            target_issue="",
            result_summary="ALERT_POSTMORTEM_FAILED",
            error_message=message,
        ),
    )
    append_alert(store, "ALERT_POSTMORTEM_FAILED", message)
