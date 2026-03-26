import json
from pathlib import Path

import pytest

from app.services.official_sync_service import _extract_issues_from_html, _merge_sources, sync_official_sources


def test_extract_issues_from_html() -> None:
    html = """
    <html><body>
      <div>25001 01 08 15 22 30 03 11</div>
      <div>25002 02 09 16 23 31 04 12</div>
    </body></html>
    """
    items = _extract_issues_from_html(html)
    assert len(items) == 2
    assert items[0].issue == "25001"
    assert items[0].front == [1, 8, 15, 22, 30]
    assert items[0].back == [3, 11]


def test_merge_sources_with_mismatch_warning() -> None:
    draw = _extract_issues_from_html("<div>25011 01 02 03 04 05 06 07</div>")
    trend = _extract_issues_from_html("<div>25011 01 02 03 04 09 06 07</div>")
    merged, warnings = _merge_sources(draw, trend)
    assert len(merged) == 1
    assert len(warnings) == 1


def test_sync_official_sources_includes_history_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    norm = tmp_path / "normalized"
    st = tmp_path / "storage"
    raw.mkdir(parents=True, exist_ok=True)
    norm.mkdir(parents=True, exist_ok=True)
    st.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("app.services.official_sync_service.raw_data_dir", lambda: raw)
    monkeypatch.setattr("app.services.official_sync_service.normalized_data_dir", lambda: norm)
    monkeypatch.setattr("app.services.official_sync_service.storage_dir", lambda: st)

    html = "<div>25001 01 02 03 04 05 06 07</div>"

    def _fake_fetch(_url: str, timeout: int = 12) -> str:
        _ = timeout
        return html

    monkeypatch.setattr("app.services.official_sync_service._fetch_html", _fake_fetch)

    def _fake_history_sync(*, limit: int = 500, page_size: int = 30, max_pages: int = 80) -> dict:
        _ = (page_size, max_pages)
        items = [
            {"issue": f"{26000 - i}", "front": [1, 2, 3, 4, 5], "back": [6, 7], "source": ["sporttery_api"]}
            for i in range(limit)
        ]
        (norm / "issues.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
        (st / "issues.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
        return {
            "ok": True,
            "degraded": False,
            "issueCount": len(items),
            "fetchedUniqueIssues": len(items),
            "warnings": [],
        }

    monkeypatch.setattr("app.services.sporttery_history_service.sync_sporttery_history", _fake_history_sync)

    out = sync_official_sources(history_limit=5)
    assert out["historySync"] is not None
    assert out["historySync"]["issueCount"] == 5
    assert out["issueCount"] == 5
    payload = json.loads((norm / "issues.json").read_text(encoding="utf-8"))
    assert len(payload["items"]) == 5
