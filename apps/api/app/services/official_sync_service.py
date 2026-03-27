from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.core.paths import normalized_data_dir, raw_data_dir, storage_dir

TREND_URL = "https://m.lottery.gov.cn/zst/dlt/"
DRAW_URL = "https://m.lottery.gov.cn/tcwm/dlt/"
RULE_URL = "https://m.lottery.gov.cn/ksjz/m/yxgz_dlt/"


@dataclass
class ParsedIssue:
    issue: str
    front: list[int]
    back: list[int]
    draw_date: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_html(url: str, timeout: int = 12) -> str:
    req = Request(
        url=url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="ignore")


def _save_raw_snapshot(prefix: str, html: str) -> dict[str, str]:
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    filename = f"{prefix}_{stamp}_{digest[:10]}.html"
    raw_path = raw_data_dir() / filename
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(html, encoding="utf-8")
    return {"file": str(raw_path), "sha256": digest}


def _load_latest_raw_snapshot(prefix: str) -> tuple[str, dict[str, str]] | None:
    candidates = sorted(raw_data_dir().glob(f"{prefix}_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    latest = candidates[0]
    html = latest.read_text(encoding="utf-8")
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    return html, {"file": str(latest), "sha256": digest}


def _extract_issues_from_html(html: str) -> list[ParsedIssue]:
    text = re.sub(r"\s+", " ", html)
    issue_pattern = re.compile(r"\b(?P<issue>\d{5,7})\b")
    num_pattern = re.compile(r"\b(0?[1-9]|[12]\d|3[0-5])\b")
    results: list[ParsedIssue] = []
    seen: set[str] = set()
    for match in issue_pattern.finditer(text):
        issue = match.group("issue")
        if issue in seen:
            continue
        start = match.end()
        window = text[start : start + 180]
        nums = [int(v) for v in num_pattern.findall(window)]
        if len(nums) < 7:
            continue
        front = nums[:5]
        back = nums[5:7]
        if len(set(front)) != 5 or len(set(back)) != 2:
            continue
        if any(n < 1 or n > 35 for n in front) or any(n < 1 or n > 12 for n in back):
            continue
        results.append(ParsedIssue(issue=issue, front=sorted(front), back=sorted(back)))
        seen.add(issue)
    return results


def _merge_sources(draw_items: list[ParsedIssue], trend_items: list[ParsedIssue]) -> tuple[list[dict[str, Any]], list[str]]:
    merged: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for src_name, items in (("draw", draw_items), ("trend", trend_items)):
        for item in items:
            if item.issue not in merged:
                merged[item.issue] = {
                    "issue": item.issue,
                    "draw_date": item.draw_date,
                    "front": item.front,
                    "back": item.back,
                    "source": [src_name],
                }
                continue
            existed = merged[item.issue]
            if existed["front"] != item.front or existed["back"] != item.back:
                warnings.append(f"Mismatch issue {item.issue} between draw/trend sources.")
                continue
            existed["source"].append(src_name)
    return sorted(merged.values(), key=lambda x: x["issue"], reverse=True), warnings


def _update_rule_versions(rule_html: str, latest_issue: str | None) -> dict[str, Any]:
    versions_path = normalized_data_dir() / "rule_versions.json"
    payload = _read_json(versions_path, default={"items": []})
    digest = hashlib.sha256(rule_html.encode("utf-8")).hexdigest()
    exists = any(item.get("sha256") == digest for item in payload["items"])
    if not exists:
        payload["items"].append(
            {
                "version_id": f"rule_{len(payload['items']) + 1:03d}",
                "sha256": digest,
                "source_url": RULE_URL,
                "detected_at": _utc_now().isoformat(),
                "effective_from_issue": latest_issue,
            }
        )
        _write_json(versions_path, payload)
    return payload


def _validate_draw_numbers(front: list[int], back: list[int]) -> tuple[bool, str]:
    if len(front) != 5 or len(back) != 2:
        return False, "invalid length"
    if len(set(front)) != 5 or len(set(back)) != 2:
        return False, "duplicate numbers"
    if any(n < 1 or n > 35 for n in front) or any(n < 1 or n > 12 for n in back):
        return False, "out of range"
    if front != sorted(front) or back != sorted(back):
        return False, "must be sorted ascending"
    return True, ""


def ingest_official_draw(
    issue: str,
    front: list[int],
    back: list[int],
    draw_date: str | None = None,
) -> dict[str, Any]:
    """
    开奖回填：合法校验、幂等、冲突不覆盖。
    写入 normalized/issues.json 与 storage/issues.json。
    """
    ok, reason = _validate_draw_numbers(front, back)
    if not ok:
        return {"ok": False, "status": "invalid", "reason": reason}

    normalized_path = normalized_data_dir() / "issues.json"
    existing = _read_json(normalized_path, default={"items": []})
    row_by_issue = {str(r["issue"]): r for r in existing.get("items", []) if "issue" in r}
    key = str(issue)
    sync_time = _utc_now().isoformat()

    if key in row_by_issue:
        prev = row_by_issue[key]
        pf = sorted(prev.get("front") or [])
        pb = sorted(prev.get("back") or [])
        if len(pf) == 5 and len(pb) == 2:
            if pf == sorted(front) and pb == sorted(back):
                return {"ok": True, "status": "idempotent", "issue": key}
            return {
                "ok": False,
                "status": "data_conflict",
                "issue": key,
                "existing": {"front": pf, "back": pb},
                "incoming": {"front": sorted(front), "back": sorted(back)},
            }

    new_row = {
        "issue": key,
        "draw_date": draw_date,
        "front": sorted(front),
        "back": sorted(back),
        "source": ["ingest"],
        "synced_at": sync_time,
    }
    row_by_issue[key] = new_row
    final_items = sorted(row_by_issue.values(), key=lambda x: str(x["issue"]), reverse=True)
    _write_json(normalized_path, {"items": final_items})
    _write_json(storage_dir() / "issues.json", {"items": final_items})
    return {"ok": True, "status": "merged", "issue": key}


def sync_official_sources(*, history_limit: int = 500) -> dict[str, Any]:
    sync_time = _utc_now().isoformat()
    warnings: list[str] = []
    snapshots: dict[str, Any] = {}
    normalized_path = normalized_data_dir() / "issues.json"
    before_payload = _read_json(normalized_path, default={"items": []})
    before_issue_ids = {str(row.get("issue")) for row in before_payload.get("items", []) if row.get("issue") is not None}
    final_items = before_payload.get("items", [])
    history_sync: dict[str, Any] | None = None
    degraded = False

    try:
        # Local import to avoid circular dependency: sporttery_history_service imports helpers from this module.
        from app.services.sporttery_history_service import sync_sporttery_history

        history_sync = sync_sporttery_history(limit=history_limit)
        warnings.extend(list(history_sync.get("warnings") or []))
        degraded = bool(history_sync.get("degraded"))
        latest_payload = _read_json(normalized_path, default={"items": []})
        final_items = latest_payload.get("items", [])
    except Exception as exc:  # noqa: BLE001
        degraded = True
        warnings.append(f"history sync failed: {exc}")

    after_issue_ids = {str(row.get("issue")) for row in final_items if row.get("issue") is not None}
    rule_versions = _read_json(normalized_data_dir() / "rule_versions.json", default={"items": []})

    return {
        "ok": not degraded and bool(final_items),
        "degraded": degraded or not final_items,
        "mode": "history_text",
        "syncedAt": (history_sync or {}).get("syncedAt", sync_time),
        "issueCount": len(final_items),
        "newIssueCount": max(0, len(after_issue_ids - before_issue_ids)),
        "ruleVersionCount": len(rule_versions.get("items", [])),
        "warnings": warnings,
        "snapshots": snapshots,
        "historySync": history_sync,
    }
