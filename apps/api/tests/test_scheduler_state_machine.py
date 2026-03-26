from __future__ import annotations

from pathlib import Path

import pytest

from app.services.json_store import JsonStore
from app.services.scheduler_audit_service import append_audit_entry, build_audit_entry, transition_task


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JsonStore:
    monkey_storage = tmp_path / "storage"
    monkey_storage.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: monkey_storage)
    return JsonStore()


def test_transition_succeeded_then_skipped(store: JsonStore) -> None:
    calls: list[int] = []

    def runner() -> dict:
        calls.append(1)
        return {"result_summary": "done", "snapshot_hash": "sh1", "model_version": "mv1"}

    r1 = transition_task(
        store,
        task_type="sync_job",
        trigger_source="manual",
        target_issue="",
        snapshot_hash="",
        model_version="na",
        date_bucket="2026-03-26",
        runner=runner,
    )
    assert r1["status"] == "succeeded"
    assert len(calls) == 1

    r2 = transition_task(
        store,
        task_type="sync_job",
        trigger_source="manual",
        target_issue="",
        snapshot_hash="",
        model_version="na",
        date_bucket="2026-03-26",
        runner=runner,
    )
    assert r2["status"] == "skipped"
    assert len(calls) == 1


def test_transition_failed_then_retry_attempt(store: JsonStore) -> None:
    n = {"i": 0}

    def runner() -> dict:
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("boom")
        return {"result_summary": "ok"}

    r1 = transition_task(
        store,
        task_type="optimize_job",
        trigger_source="retry",
        target_issue="",
        snapshot_hash="",
        model_version="mv",
        date_bucket="b1",
        runner=runner,
    )
    assert r1["status"] == "failed"

    r2 = transition_task(
        store,
        task_type="optimize_job",
        trigger_source="retry",
        target_issue="",
        snapshot_hash="",
        model_version="mv",
        date_bucket="b1",
        runner=runner,
    )
    assert r2["status"] == "succeeded"
    logs = store.read("scheduler_logs.json", default={"logs": []})["logs"]
    attempts = [x for x in logs if x.get("task_type") == "optimize_job" and x.get("status") == "succeeded"]
    assert attempts
    assert attempts[-1].get("attempt_no") == 2


def test_audit_entry_has_required_fields(store: JsonStore) -> None:
    append_audit_entry(
        store,
        build_audit_entry(
            task_id="t1",
            task_type="sync_job",
            trigger_source="schedule",
            status="queued",
            idempotency_key="k",
            target_issue="25100",
            snapshot_hash="sh",
            model_version="mv",
            duration_ms=10,
            attempt_no=1,
            result_summary="q",
            warnings=["w"],
            error_message="",
        ),
    )
    logs = store.read("scheduler_logs.json", default={"logs": []})["logs"]
    e = logs[-1]
    for k in (
        "task_id",
        "task_type",
        "trigger_source",
        "status",
        "target_issue",
        "snapshot_hash",
        "model_version",
        "duration_ms",
        "attempt_no",
        "result_summary",
        "warnings",
        "error_message",
        "created_at",
    ):
        assert k in e
