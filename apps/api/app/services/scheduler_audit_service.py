from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from app.services.json_store import JsonStore

TaskStatus = Literal["queued", "running", "succeeded", "failed", "skipped", "compensated"]
TriggerSource = Literal["schedule", "manual", "retry", "chained"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_idempotency_key(
    *,
    task_type: str,
    target_issue: str,
    snapshot_hash: str,
    model_version: str,
    date_bucket: str,
) -> str:
    raw = f"{task_type}|{target_issue}|{snapshot_hash}|{model_version}|{date_bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _default_logs_payload() -> dict[str, Any]:
    return {
        "logs": [],
        "idempotency": {},
        "alert_state": {"consecutive_sync_failures": 0, "last_alerts": []},
    }


def _load_logs_payload(store: JsonStore) -> dict[str, Any]:
    data = store.read("scheduler_logs.json", default=_default_logs_payload())
    data.setdefault("logs", [])
    data.setdefault("idempotency", {})
    data.setdefault("alert_state", {"consecutive_sync_failures": 0, "last_alerts": []})
    return data


def _write_logs_payload(store: JsonStore, payload: dict[str, Any]) -> None:
    store.write("scheduler_logs.json", payload)


def get_idempotency_record(store: JsonStore, key: str) -> dict[str, Any] | None:
    payload = _load_logs_payload(store)
    rec = payload["idempotency"].get(key)
    return dict(rec) if rec else None


def set_idempotency_record(store: JsonStore, key: str, record: dict[str, Any]) -> None:
    payload = _load_logs_payload(store)
    payload["idempotency"][key] = record
    _write_logs_payload(store, payload)


def append_alert(store: JsonStore, code: str, summary: str) -> None:
    payload = _load_logs_payload(store)
    alerts = payload["alert_state"].setdefault("last_alerts", [])
    alerts.append({"code": code, "summary": summary, "at": utc_now_iso()})
    payload["alert_state"]["last_alerts"] = alerts[-50:]
    _write_logs_payload(store, payload)


def record_sync_failure_for_alerts(store: JsonStore, succeeded: bool) -> list[str]:
    """Returns new alert codes emitted."""
    payload = _load_logs_payload(store)
    st = payload["alert_state"]
    if succeeded:
        st["consecutive_sync_failures"] = 0
    else:
        st["consecutive_sync_failures"] = int(st.get("consecutive_sync_failures", 0)) + 1
    emitted: list[str] = []
    if st["consecutive_sync_failures"] >= 2:
        append_alert(store, "ALERT_SYNC_DEGRADED", "consecutive sync_job failures >= 2")
        emitted.append("ALERT_SYNC_DEGRADED")
    _write_logs_payload(store, payload)
    return emitted


def build_audit_entry(
    *,
    task_id: str,
    task_type: str,
    trigger_source: TriggerSource,
    status: TaskStatus,
    idempotency_key: str,
    target_issue: str = "",
    snapshot_hash: str = "",
    model_version: str = "",
    duration_ms: int = 0,
    attempt_no: int = 1,
    result_summary: str = "",
    warnings: list[str] | None = None,
    error_message: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "task_type": task_type,
        "trigger_source": trigger_source,
        "status": status,
        "target_issue": target_issue,
        "snapshot_hash": snapshot_hash,
        "model_version": model_version,
        "duration_ms": duration_ms,
        "attempt_no": attempt_no,
        "result_summary": result_summary,
        "warnings": warnings or [],
        "error_message": error_message,
        "idempotency_key": idempotency_key,
        "created_at": created_at or utc_now_iso(),
    }


def append_audit_entry(store: JsonStore, entry: dict[str, Any]) -> None:
    payload = _load_logs_payload(store)
    payload["logs"].append(entry)
    _write_logs_payload(store, payload)


def transition_task(
    store: JsonStore,
    *,
    task_type: str,
    trigger_source: TriggerSource,
    target_issue: str,
    snapshot_hash: str,
    model_version: str,
    date_bucket: str,
    runner: Any,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """
    Unified state machine: queued -> running -> succeeded|failed|skipped|compensated.
    `runner` is a callable () -> dict with keys: result_summary, warnings (opt), snapshot_hash (opt),
    model_version (opt), task_status (opt; one of succeeded|failed), error_message (opt).
    On exception -> failed.
    """
    ikey = idempotency_key or compute_idempotency_key(
        task_type=task_type,
        target_issue=target_issue,
        snapshot_hash=snapshot_hash,
        model_version=model_version,
        date_bucket=date_bucket,
    )
    existing = get_idempotency_record(store, ikey)
    attempt_no = 1
    if existing:
        if existing.get("status") == "succeeded":
            task_id = str(existing.get("task_id") or uuid.uuid4().hex)
            entry = build_audit_entry(
                task_id=task_id,
                task_type=task_type,
                trigger_source=trigger_source,
                status="skipped",
                idempotency_key=ikey,
                target_issue=target_issue,
                snapshot_hash=snapshot_hash,
                model_version=model_version,
                attempt_no=int(existing.get("attempt_no", 1)),
                result_summary="idempotent skip: prior success",
            )
            append_audit_entry(store, entry)
            return {"status": "skipped", "task_id": task_id, "idempotency_key": ikey}
        attempt_no = int(existing.get("attempt_no", 0)) + 1

    task_id = uuid.uuid4().hex
    started = utc_now_iso()
    append_audit_entry(
        store,
        build_audit_entry(
            task_id=task_id,
            task_type=task_type,
            trigger_source=trigger_source,
            status="running",
            idempotency_key=ikey,
            target_issue=target_issue,
            snapshot_hash=snapshot_hash,
            model_version=model_version,
            attempt_no=attempt_no,
            result_summary="started",
            created_at=started,
        ),
    )
    import time

    t0 = time.perf_counter()
    try:
        out = runner()
        duration_ms = int((time.perf_counter() - t0) * 1000)
        sh = str(out.get("snapshot_hash") or snapshot_hash)
        mv = str(out.get("model_version") or model_version)
        summary = str(out.get("result_summary") or "ok")
        warnings = list(out.get("warnings") or [])
        task_status = str(out.get("task_status") or "succeeded")
        if task_status not in ("succeeded", "failed"):
            task_status = "succeeded"
        error_message = str(out.get("error_message") or "")
        entry = build_audit_entry(
            task_id=task_id,
            task_type=task_type,
            trigger_source=trigger_source,
            status=task_status,
            idempotency_key=ikey,
            target_issue=target_issue,
            snapshot_hash=sh,
            model_version=mv,
            duration_ms=duration_ms,
            attempt_no=attempt_no,
            result_summary=summary,
            warnings=warnings,
            error_message=error_message,
        )
        append_audit_entry(store, entry)
        set_idempotency_record(
            store,
            ikey,
            {
                "status": task_status,
                "task_id": task_id,
                "attempt_no": attempt_no,
                "finished_at": utc_now_iso(),
                **({"error_message": error_message} if error_message else {}),
            },
        )
        return {"status": task_status, "task_id": task_id, "idempotency_key": ikey, "detail": out}
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - t0) * 1000)
        entry = build_audit_entry(
            task_id=task_id,
            task_type=task_type,
            trigger_source=trigger_source,
            status="failed",
            idempotency_key=ikey,
            target_issue=target_issue,
            snapshot_hash=snapshot_hash,
            model_version=model_version,
            duration_ms=duration_ms,
            attempt_no=attempt_no,
            result_summary="failed",
            error_message=str(exc),
        )
        append_audit_entry(store, entry)
        set_idempotency_record(
            store,
            ikey,
            {
                "status": "failed",
                "task_id": task_id,
                "attempt_no": attempt_no,
                "finished_at": utc_now_iso(),
                "error_message": str(exc),
            },
        )
        return {"status": "failed", "task_id": task_id, "idempotency_key": ikey, "error": str(exc)}
