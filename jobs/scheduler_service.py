from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.automation_pipeline import (  # noqa: E402
    resolve_next_target_issue,
    run_draw_poll_job,
    run_draw_poll_and_chain,
    run_postmortem_job,
    run_promotion_eval_job,
    run_publish_check_job,
    run_sync_job,
    run_optimize_job,
)
from app.services.json_store import JsonStore  # noqa: E402


def _store() -> JsonStore:
    return JsonStore()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="dlt-evolution-lab scheduler jobs")
    p.add_argument(
        "job",
        choices=[
            "sync_job",
            "publish_check_job",
            "draw_poll_job",
            "postmortem_job",
            "optimize_job",
            "promotion_eval_job",
        ],
    )
    p.add_argument("--issue", default="", help="target issue for publish/draw/postmortem")
    p.add_argument("--front", default="", help="comma-separated front numbers for draw_poll_job")
    p.add_argument("--back", default="", help="comma-separated back numbers for draw_poll_job")
    p.add_argument("--draw-date", default="", dest="draw_date")
    p.add_argument(
        "--trigger",
        default="schedule",
        choices=["schedule", "manual", "retry", "chained"],
    )
    args = p.parse_args(argv)
    store = _store()
    trigger: Literal["schedule", "manual", "retry", "chained"] = args.trigger  # type: ignore[assignment]

    out: dict[str, Any]
    if args.job == "sync_job":
        out = run_sync_job(store, trigger_source=trigger)
    elif args.job == "publish_check_job":
        issue = args.issue or resolve_next_target_issue(store)
        out = run_publish_check_job(store, target_issue=issue, trigger_source=trigger)
    elif args.job == "draw_poll_job":
        if args.front and args.back:
            if not args.issue:
                print("draw_poll_job manual mode requires --issue with --front/--back", file=sys.stderr)
                return 2
            front = [int(x.strip()) for x in args.front.split(",") if x.strip()]
            back = [int(x.strip()) for x in args.back.split(",") if x.strip()]
            dd = args.draw_date or None
            out = run_draw_poll_and_chain(
                store,
                target_issue=args.issue,
                front=front,
                back=back,
                draw_date=dd,
                trigger_source=trigger,
            )
        else:
            out = run_draw_poll_job(store, target_issue=args.issue, trigger_source=trigger)
    elif args.job == "postmortem_job":
        if not args.issue:
            print("postmortem_job requires --issue", file=sys.stderr)
            return 2
        out = run_postmortem_job(store, issue=args.issue, trigger_source=trigger)
    elif args.job == "optimize_job":
        out = run_optimize_job(store, trigger_source=trigger, reason="scheduler")
    else:
        out = run_promotion_eval_job(store, trigger_source=trigger)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    if "ingest" in out:
        st = (out.get("ingest") or {}).get("status")
        return 0 if st in ("succeeded", "skipped") else 1
    st = out.get("status")
    return 0 if st in (None, "succeeded", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
