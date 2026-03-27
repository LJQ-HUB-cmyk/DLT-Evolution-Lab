from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

import pytest

from app.services.sporttery_history_service import parse_sporttery_draw_result, sync_sporttery_history


def test_parse_sporttery_draw_result_plus_form() -> None:
    p = parse_sporttery_draw_result("05 12 18 22 35+04 09")
    assert p is not None
    front, back = p
    assert front == [5, 12, 18, 22, 35]
    assert back == [4, 9]


def test_parse_sporttery_draw_result_space_seven() -> None:
    p = parse_sporttery_draw_result("01 08 15 22 30 03 11")
    assert p is not None
    assert p[0] == [1, 8, 15, 22, 30]
    assert p[1] == [3, 11]


def test_parse_sporttery_draw_result_invalid() -> None:
    assert parse_sporttery_draw_result("") is None
    assert parse_sporttery_draw_result("1 2 3") is None


def test_sync_sporttery_history_merges_and_trims(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    norm = tmp_path / "normalized"
    norm.mkdir(parents=True)
    st = tmp_path / "storage"
    st.mkdir(parents=True)

    monkeypatch.setattr("app.services.sporttery_history_service.normalized_data_dir", lambda: norm)
    monkeypatch.setattr("app.services.sporttery_history_service.storage_dir", lambda: st)

    (norm / "issues.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "issue": "10001",
                        "front": [1, 2, 3, 4, 5],
                        "back": [6, 7],
                        "source": ["legacy"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def _fake_text() -> str:
        lines = []
        for n in range(25000, 25008):
            lines.append(f"{n} 2026-01-01 01 02 03 04 05 06 07 - - -")
        return "\n".join(lines)

    monkeypatch.setattr("app.services.sporttery_history_service._fetch_history_text", _fake_text)

    out = sync_sporttery_history(limit=5, page_size=30, max_pages=10)
    assert out["ok"] is True
    assert out["issueCount"] == 5
    assert out["fetchedUniqueIssues"] >= 5

    payload = json.loads((norm / "issues.json").read_text(encoding="utf-8"))
    issues = [str(x["issue"]) for x in payload["items"]]
    assert len(issues) == 5
    assert "10001" not in issues
    assert issues == sorted(issues, key=int, reverse=True)

    st_payload = json.loads((st / "issues.json").read_text(encoding="utf-8"))
    assert len(st_payload["items"]) == 5


def test_sync_sporttery_history_conflict_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    norm = tmp_path / "normalized"
    norm.mkdir(parents=True)
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.services.sporttery_history_service.normalized_data_dir", lambda: norm)
    monkeypatch.setattr("app.services.sporttery_history_service.storage_dir", lambda: st)

    (norm / "issues.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "issue": "25001",
                        "front": [10, 11, 12, 13, 14],
                        "back": [1, 2],
                        "source": ["local"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def _fake_text() -> str:
        return "25001 2026-01-02 01 02 03 04 05 06 07 - - -"

    monkeypatch.setattr("app.services.sporttery_history_service._fetch_history_text", _fake_text)

    out = sync_sporttery_history(limit=10, page_size=30, max_pages=1)
    assert out["conflictsSkipped"] == 1
    assert any("data_conflict" in w for w in out["warnings"])
    payload = json.loads((norm / "issues.json").read_text(encoding="utf-8"))
    row = payload["items"][0]
    assert row["front"] == [10, 11, 12, 13, 14]


def test_sync_sporttery_history_handles_blocked_text_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    norm = tmp_path / "normalized"
    norm.mkdir(parents=True)
    st = tmp_path / "storage"
    st.mkdir(parents=True)

    monkeypatch.setattr("app.services.sporttery_history_service.normalized_data_dir", lambda: norm)
    monkeypatch.setattr("app.services.sporttery_history_service.storage_dir", lambda: st)

    (norm / "issues.json").write_text(
        json.dumps({"items": [{"issue": "25130", "front": [1, 2, 3, 4, 5], "back": [6, 7], "source": ["ingest"]}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    def _raise_fetch() -> str:
        raise URLError("HTTP Error 567: Unknown Status")

    monkeypatch.setattr("app.services.sporttery_history_service._fetch_history_text", _raise_fetch)

    out = sync_sporttery_history(limit=10)
    assert out["ok"] is False
    assert out["issueCount"] == 1
    assert out["fetchedUniqueIssues"] == 0
    assert any("history text fetch failed" in w for w in out["warnings"])


def test_sync_sporttery_history_replaces_ingest_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    norm = tmp_path / "normalized"
    norm.mkdir(parents=True)
    st = tmp_path / "storage"
    st.mkdir(parents=True)

    monkeypatch.setattr("app.services.sporttery_history_service.normalized_data_dir", lambda: norm)
    monkeypatch.setattr("app.services.sporttery_history_service.storage_dir", lambda: st)

    (norm / "issues.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "issue": "25130",
                        "front": [1, 2, 3, 4, 5],
                        "back": [6, 7],
                        "draw_date": None,
                        "source": ["ingest"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def _fake_text() -> str:
        return "25130 2025-11-01 08 11 15 22 31 04 09 - - -"

    monkeypatch.setattr("app.services.sporttery_history_service._fetch_history_text", _fake_text)

    out = sync_sporttery_history(limit=10)
    assert any("replaced ingest placeholder" in w for w in out["warnings"])
    payload = json.loads((norm / "issues.json").read_text(encoding="utf-8"))
    row = payload["items"][0]
    assert row["front"] == [8, 11, 15, 22, 31]
    assert row["back"] == [4, 9]
    assert row["source"] == ["data17500_txt"]


def test_sync_sporttery_history_uses_incremental_merge_when_local_cache_is_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    norm = tmp_path / "normalized"
    norm.mkdir(parents=True)
    st = tmp_path / "storage"
    st.mkdir(parents=True)

    monkeypatch.setattr("app.services.sporttery_history_service.normalized_data_dir", lambda: norm)
    monkeypatch.setattr("app.services.sporttery_history_service.storage_dir", lambda: st)

    existing_items = []
    for n in range(25000, 25005):
        existing_items.append(
            {
                "issue": str(n),
                "front": [1, 2, 3, 4, 5],
                "back": [6, 7],
                "draw_date": "2026-01-01",
                "source": ["data17500_txt"],
            }
        )
    (norm / "issues.json").write_text(json.dumps({"items": existing_items}, ensure_ascii=False), encoding="utf-8")

    def _fake_text() -> str:
        lines = []
        for n in range(25000, 25008):
            lines.append(f"{n} 2026-01-01 01 02 03 04 05 06 07 - - -")
        return "\n".join(lines)

    monkeypatch.setattr("app.services.sporttery_history_service._fetch_history_text", _fake_text)

    out = sync_sporttery_history(limit=5)
    assert out["ok"] is True
    assert out["incrementalApplied"] is True
    assert out["fetchedUniqueIssues"] == 3
    assert out["incrementalAnchorIssue"] == "25004"

    payload = json.loads((norm / "issues.json").read_text(encoding="utf-8"))
    issues = [str(x["issue"]) for x in payload["items"]]
    assert issues == ["25007", "25006", "25005", "25004", "25003"]
