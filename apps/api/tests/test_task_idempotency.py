from __future__ import annotations

from pathlib import Path

import pytest

from app.services.json_store import JsonStore
from app.services.scheduler_audit_service import compute_idempotency_key, get_idempotency_record, transition_task


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JsonStore:
    st = tmp_path / "storage"
    st.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    return JsonStore()


def test_same_key_after_success_skips(store: JsonStore) -> None:
    key = compute_idempotency_key(
        task_type="t",
        target_issue="25101",
        snapshot_hash="sh",
        model_version="mv",
        date_bucket="d",
    )

    def ok() -> dict:
        return {"result_summary": "ok", "snapshot_hash": "sh", "model_version": "mv"}

    r1 = transition_task(
        store,
        task_type="t",
        trigger_source="manual",
        target_issue="25101",
        snapshot_hash="sh",
        model_version="mv",
        date_bucket="d",
        runner=ok,
        idempotency_key=key,
    )
    assert r1["status"] == "succeeded"
    rec = get_idempotency_record(store, key)
    assert rec and rec.get("status") == "succeeded"

    r2 = transition_task(
        store,
        task_type="t",
        trigger_source="manual",
        target_issue="25101",
        snapshot_hash="sh",
        model_version="mv",
        date_bucket="d",
        runner=ok,
        idempotency_key=key,
    )
    assert r2["status"] == "skipped"
