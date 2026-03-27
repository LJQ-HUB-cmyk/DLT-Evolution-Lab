from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.core.paths import normalized_data_dir, storage_dir
from app.services.official_sync_service import _read_json, _validate_draw_numbers, _write_json

# 超级大乐透历史文本源，按期号升序返回。
HISTORY_TEXT_URL = "https://data.17500.cn/dlt_asc.txt"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_sporttery_draw_result(raw: str) -> tuple[list[int], list[int]] | None:
    """Parse lotteryDrawResult like '05 12 18 22 35+04 09' or seven spaced ints."""
    s = (raw or "").strip()
    if not s:
        return None
    if "+" in s:
        left, right = s.split("+", 1)
        front = [int(x) for x in re.findall(r"\d+", left)]
        back = [int(x) for x in re.findall(r"\d+", right)]
    else:
        nums = [int(x) for x in re.findall(r"\d+", s)]
        if len(nums) < 7:
            return None
        front, back = nums[:5], nums[5:7]
    if len(front) != 5 or len(back) != 2:
        return None
    front_s = sorted(front)
    back_s = sorted(back)
    ok, _ = _validate_draw_numbers(front_s, back_s)
    if not ok:
        return None
    return front_s, back_s


def _fetch_history_text(timeout: int = 20) -> str:
    req = Request(
        url=HISTORY_TEXT_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/plain,text/html,application/xhtml+xml",
        },
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="ignore")


def _numeric_issue(issue: str) -> int:
    try:
        return int(str(issue).strip())
    except (TypeError, ValueError):
        return -1


def _parse_history_text(raw_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in (raw_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 9:
            continue
        issue = str(parts[0]).strip()
        draw_date = str(parts[1]).strip()
        try:
            front = sorted(int(x) for x in parts[2:7])
            back = sorted(int(x) for x in parts[7:9])
        except ValueError:
            continue
        ok, _ = _validate_draw_numbers(front, back)
        if not ok or issue in seen:
            continue
        rows.append(
            {
                "issue": issue,
                "front": front,
                "back": back,
                "draw_date": draw_date,
            }
        )
        seen.add(issue)
    return rows


def _collect_incremental_rows(raw_text: str, latest_issue: str | None) -> tuple[list[dict[str, Any]], int, bool]:
    """
    Read the text source from the end and collect only issues newer than ``latest_issue``.
    Returns: (rows, scanned_lines, anchor_found)
    """
    if not raw_text:
        return [], 0, False
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return [], 0, False
    if not latest_issue:
        return _parse_history_text(raw_text), len(lines), False

    rows_reversed: list[dict[str, Any]] = []
    seen: set[str] = set()
    scanned = 0
    anchor_found = False

    for line in reversed(lines):
        scanned += 1
        parts = line.split()
        if len(parts) < 9:
            continue
        issue = str(parts[0]).strip()
        if issue == str(latest_issue).strip():
            anchor_found = True
            break
        try:
            front = sorted(int(x) for x in parts[2:7])
            back = sorted(int(x) for x in parts[7:9])
        except ValueError:
            continue
        ok, _ = _validate_draw_numbers(front, back)
        if not ok or issue in seen:
            continue
        rows_reversed.append(
            {
                "issue": issue,
                "front": front,
                "back": back,
                "draw_date": str(parts[1]).strip(),
            }
        )
        seen.add(issue)

    rows_reversed.reverse()
    return rows_reversed, scanned, anchor_found


def sync_sporttery_history(
    *,
    limit: int = 500,
    page_size: int = 30,
    max_pages: int = 80,
) -> dict[str, Any]:
    """
    Pull DLT draw history from the configured text source, merge into normalized + storage issues,
    then keep only the ``limit`` highest issue numbers (most recent periods).
    """
    limit = max(1, min(int(limit), 3000))
    page_size = max(10, min(int(page_size), 100))
    max_pages = max(1, min(int(max_pages), 200))
    _ = (page_size, max_pages)

    warnings: list[str] = []
    sync_time = _utc_now().isoformat()
    normalized_path = normalized_data_dir() / "issues.json"
    existing = _read_json(normalized_path, default={"items": []})
    existing_items = list(existing.get("items", []))
    row_by_issue: dict[str, dict[str, Any]] = {
        str(r["issue"]): dict(r) for r in existing_items if r.get("issue") is not None
    }
    latest_existing_issue = None
    latest_existing_row: dict[str, Any] | None = None
    if existing_items:
        latest_existing_row = max(
            (dict(r) for r in existing_items if r.get("issue") is not None),
            key=lambda r: _numeric_issue(str(r.get("issue"))),
        )
        latest_existing_issue = str(latest_existing_row.get("issue"))
    can_use_incremental = bool(
        latest_existing_issue
        and len(existing_items) >= limit
        and "ingest" not in {str(x) for x in ((latest_existing_row or {}).get("source") or [])}
    )

    fetched: dict[str, dict[str, Any]] = {}
    parsed_rows = 0
    degraded = False
    incremental_mode = False
    anchor_found = False
    scanned_lines = 0

    try:
        raw_text = _fetch_history_text()
    except (URLError, OSError, ValueError) as exc:
        degraded = True
        warnings.append(f"history text fetch failed: {exc}")
        raw_text = ""

    if raw_text:
        rows, scanned_lines, anchor_found = _collect_incremental_rows(raw_text, latest_existing_issue if can_use_incremental else None)
        incremental_mode = bool(can_use_incremental and anchor_found)
        if can_use_incremental and latest_existing_issue and not anchor_found:
            warnings.append("incremental anchor not found, fallback to full rebuild")
            rows = _parse_history_text(raw_text)
            parsed_rows = len(rows)
        else:
            parsed_rows = len(rows)
    else:
        rows = []
    parsed_rows = len(rows)
    if not rows:
        if can_use_incremental and latest_existing_issue and anchor_found:
            warnings.append("no new draws found beyond local latest issue")
        else:
            degraded = True
            warnings.append("no draws parsed from history text source")

    for row in rows:
        issue = str(row.get("issue") or "").strip()
        if not issue:
            continue
        if issue in fetched:
            prev_f, prev_b = fetched[issue]["front"], fetched[issue]["back"]
            if prev_f != row["front"] or prev_b != row["back"]:
                warnings.append(f"history text duplicate issue {issue} with conflicting numbers")
            continue
        fetched[issue] = row

    if not fetched:
        if can_use_incremental and latest_existing_issue and anchor_found:
            warnings.append("no incremental draws fetched from history text source")
        else:
            degraded = True
            warnings.append("no draws fetched from history text source")

    conflicts = 0
    for issue, data in fetched.items():
        if issue not in row_by_issue:
            row_by_issue[issue] = {
                "issue": issue,
                "front": data["front"],
                "back": data["back"],
                "draw_date": data.get("draw_date"),
                "source": ["data17500_txt"],
                "synced_at": sync_time,
            }
            continue
        prev = row_by_issue[issue]
        pf = sorted(prev.get("front") or [])
        pb = sorted(prev.get("back") or [])
        if len(pf) == 5 and len(pb) == 2 and pf == data["front"] and pb == data["back"]:
            src = sorted(set((prev.get("source") or []) + ["data17500_txt"]))
            row_by_issue[issue] = {**prev, "source": src, "synced_at": sync_time}
        elif len(pf) == 5 and len(pb) == 2:
            prev_sources = set(str(x) for x in (prev.get("source") or []))
            if prev_sources == {"ingest"}:
                row_by_issue[issue] = {
                    **prev,
                    "front": data["front"],
                    "back": data["back"],
                    "draw_date": data.get("draw_date"),
                    "source": ["data17500_txt"],
                    "synced_at": sync_time,
                }
                warnings.append(f"data_conflict issue {issue}: replaced ingest placeholder with history text source")
                continue
            conflicts += 1
            warnings.append(f"data_conflict issue {issue}: kept existing, history text differed")

    final_items = sorted(row_by_issue.values(), key=lambda x: _numeric_issue(str(x.get("issue", ""))), reverse=True)
    trimmed = final_items[:limit]

    _write_json(normalized_path, {"items": trimmed})
    _write_json(storage_dir() / "issues.json", {"items": trimmed})

    return {
        "ok": not degraded,
        "degraded": degraded,
        "syncedAt": sync_time,
        "source": "data17500_txt",
        "requestedLimit": limit,
        "fetchedUniqueIssues": len(fetched),
        "apiRowsParsed": parsed_rows,
        "scannedLines": scanned_lines,
        "incrementalApplied": incremental_mode,
        "incrementalAnchorIssue": latest_existing_issue,
        "issueCount": len(trimmed),
        "conflictsSkipped": conflicts,
        "warnings": warnings,
    }
