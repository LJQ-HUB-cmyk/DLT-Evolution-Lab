from app.services.official_sync_service import _extract_issues_from_html, _merge_sources


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

