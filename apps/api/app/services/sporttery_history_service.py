from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.core.paths import normalized_data_dir, storage_dir
from app.services.official_sync_service import _read_json, _validate_draw_numbers, _write_json

# 超级大乐透 — 体彩公开网关分页接口（公开页面常用 gameNo=85）
SPORTTERY_HISTORY_URL = (
    "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
    "?gameNo=85&provinceId=0&pageSize={page_size}&isVerify=1&pageNo={page_no}"
)


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


def _fetch_sporttery_page(page_no: int, page_size: int, timeout: int = 20) -> dict[str, Any]:
    url = SPORTTERY_HISTORY_URL.format(page_no=page_no, page_size=page_size)
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _numeric_issue(issue: str) -> int:
    try:
        return int(str(issue).strip())
    except (TypeError, ValueError):
        return -1


def _page_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    val = payload.get("value")
    if not isinstance(val, dict):
        return []
    lst = val.get("list")
    return lst if isinstance(lst, list) else []


def sync_sporttery_history(
    *,
    limit: int = 500,
    page_size: int = 30,
    max_pages: int = 80,
) -> dict[str, Any]:
    """
    Pull recent DLT draws from sporttery gateway, merge into normalized + storage issues,
    then keep only the ``limit`` highest issue numbers (most recent periods).
    """
    limit = max(1, min(int(limit), 3000))
    page_size = max(10, min(int(page_size), 100))
    max_pages = max(1, min(int(max_pages), 200))

    warnings: list[str] = []
    sync_time = _utc_now().isoformat()
    normalized_path = normalized_data_dir() / "issues.json"
    existing = _read_json(normalized_path, default={"items": []})
    row_by_issue: dict[str, dict[str, Any]] = {
        str(r["issue"]): dict(r) for r in existing.get("items", []) if r.get("issue") is not None
    }

    fetched: dict[str, dict[str, Any]] = {}
    api_rows_seen = 0
    degraded = False

    for page_no in range(1, max_pages + 1):
        if len(fetched) >= limit:
            break
        try:
            payload = _fetch_sporttery_page(page_no, page_size)
        except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            degraded = True
            warnings.append(f"sporttery page {page_no} failed: {exc}")
            break

        err = payload.get("errorCode")
        if err not in (None, "0", 0):
            degraded = True
            warnings.append(f"sporttery errorCode={err} on page {page_no}")

        rows = _page_rows(payload)
        if not rows:
            break

        new_on_page = 0
        for row in rows:
            if row.get("lotteryDrawStatus") != 20:
                continue
            issue = str(row.get("lotteryDrawNum") or "").strip()
            raw_res = row.get("lotteryDrawResult") or ""
            parsed = parse_sporttery_draw_result(str(raw_res))
            if not issue or parsed is None:
                continue
            front, back = parsed
            draw_time = row.get("lotteryDrawTime")
            draw_date = draw_time if isinstance(draw_time, str) else None
            api_rows_seen += 1
            if issue in fetched:
                prev_f, prev_b = fetched[issue]["front"], fetched[issue]["back"]
                if prev_f != front or prev_b != back:
                    warnings.append(f"sporttery duplicate issue {issue} with conflicting numbers")
                continue
            fetched[issue] = {
                "issue": issue,
                "front": front,
                "back": back,
                "draw_date": draw_date,
            }
            new_on_page += 1
            if len(fetched) >= limit:
                break

        if new_on_page == 0 and rows:
            warnings.append(f"sporttery page {page_no} had rows but none parsed as completed DLT draws")
        # Do not stop just because len(rows) < page_size: some environments return short pages every time.
        # Rely on empty ``rows``, ``max_pages``, or ``len(fetched) >= limit`` instead.

    if not fetched:
        degraded = True
        warnings.append("no draws fetched from sporttery API")

    conflicts = 0
    for issue, data in fetched.items():
        if issue not in row_by_issue:
            row_by_issue[issue] = {
                "issue": issue,
                "front": data["front"],
                "back": data["back"],
                "draw_date": data.get("draw_date"),
                "source": ["sporttery_api"],
                "synced_at": sync_time,
            }
            continue
        prev = row_by_issue[issue]
        pf = sorted(prev.get("front") or [])
        pb = sorted(prev.get("back") or [])
        if len(pf) == 5 and len(pb) == 2 and pf == data["front"] and pb == data["back"]:
            src = sorted(set((prev.get("source") or []) + ["sporttery_api"]))
            row_by_issue[issue] = {**prev, "source": src, "synced_at": sync_time}
        elif len(pf) == 5 and len(pb) == 2:
            conflicts += 1
            warnings.append(f"data_conflict issue {issue}: kept existing, sporttery differed")

    final_items = sorted(row_by_issue.values(), key=lambda x: _numeric_issue(str(x.get("issue", ""))), reverse=True)
    trimmed = final_items[:limit]

    _write_json(normalized_path, {"items": trimmed})
    _write_json(storage_dir() / "issues.json", {"items": trimmed})

    return {
        "ok": not degraded,
        "degraded": degraded,
        "syncedAt": sync_time,
        "source": "sporttery_api",
        "requestedLimit": limit,
        "fetchedUniqueIssues": len(fetched),
        "apiRowsParsed": api_rows_seen,
        "issueCount": len(trimmed),
        "conflictsSkipped": conflicts,
        "warnings": warnings,
    }
