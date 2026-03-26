from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.official_sync_service import ingest_official_draw


@pytest.fixture
def norm_and_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    nd = tmp_path / "norm"
    nd.mkdir(parents=True, exist_ok=True)
    st = tmp_path / "storage"
    st.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.normalized_data_dir", lambda: nd)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    # official_sync_service imported path fns at module load — patch both.
    monkeypatch.setattr("app.services.official_sync_service.normalized_data_dir", lambda: nd)
    monkeypatch.setattr("app.services.official_sync_service.storage_dir", lambda: st)
    (nd / "issues.json").write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
    (st / "issues.json").write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
    return nd, st


def test_ingest_idempotent(norm_and_storage) -> None:
    r1 = ingest_official_draw("25110", [1, 2, 3, 4, 5], [6, 7])
    assert r1["status"] == "merged"
    r2 = ingest_official_draw("25110", [1, 2, 3, 4, 5], [6, 7])
    assert r2["status"] == "idempotent"


def test_ingest_conflict(norm_and_storage) -> None:
    ingest_official_draw("25111", [1, 2, 3, 4, 5], [6, 7])
    r = ingest_official_draw("25111", [2, 3, 4, 5, 6], [6, 7])
    assert r["status"] == "data_conflict"


def test_ingest_invalid(norm_and_storage) -> None:
    r = ingest_official_draw("25112", [1, 1, 2, 3, 4], [6, 7])
    assert r["ok"] is False
