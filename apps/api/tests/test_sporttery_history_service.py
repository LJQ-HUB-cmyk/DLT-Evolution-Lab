from __future__ import annotations

import json
from pathlib import Path

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

    def _fake_page(page_no: int, page_size: int) -> dict:
        base = 25000 + (page_no - 1) * 3
        lst = []
        for i in range(3):
            n = base + i
            lst.append(
                {
                    "lotteryDrawNum": str(n),
                    "lotteryDrawResult": "01 02 03 04 05+06 07",
                    "lotteryDrawStatus": 20,
                    "lotteryDrawTime": "2026-01-01",
                }
            )
        return {"errorCode": "0", "value": {"list": lst}}

    monkeypatch.setattr(
        "app.services.sporttery_history_service._fetch_sporttery_page",
        _fake_page,
    )

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

    def _fake_page(_page_no: int, _page_size: int) -> dict:
        return {
            "errorCode": "0",
            "value": {
                "list": [
                    {
                        "lotteryDrawNum": "25001",
                        "lotteryDrawResult": "01 02 03 04 05+06 07",
                        "lotteryDrawStatus": 20,
                        "lotteryDrawTime": "2026-01-02",
                    }
                ]
            },
        }

    monkeypatch.setattr("app.services.sporttery_history_service._fetch_sporttery_page", _fake_page)

    out = sync_sporttery_history(limit=10, page_size=30, max_pages=1)
    assert out["conflictsSkipped"] == 1
    assert any("data_conflict" in w for w in out["warnings"])
    payload = json.loads((norm / "issues.json").read_text(encoding="utf-8"))
    row = payload["items"][0]
    assert row["front"] == [10, 11, 12, 13, 14]
