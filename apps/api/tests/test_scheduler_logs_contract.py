from __future__ import annotations

from pathlib import Path

import pytest

from app.services.json_store import JsonStore
from app.services.scheduler_audit_service import transition_task

REQUIRED = (
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
)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JsonStore:
    st = tmp_path / "storage"
    st.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    return JsonStore()


def test_task_logs_contain_all_required_fields(store: JsonStore) -> None:
    def runner() -> dict:
        return {"result_summary": "x", "warnings": [], "snapshot_hash": "s", "model_version": "m"}

    transition_task(
        store,
        task_type="postmortem_job",
        trigger_source="schedule",
        target_issue="25150",
        snapshot_hash="s",
        model_version="m",
        date_bucket="25150",
        runner=runner,
    )
    logs = store.read("scheduler_logs.json", default={"logs": []})["logs"]
    task_logs = [e for e in logs if e.get("task_type") == "postmortem_job"]
    assert task_logs
    for e in task_logs:
        missing = [k for k in REQUIRED if k not in e]
        assert not missing, missing
