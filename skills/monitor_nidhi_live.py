#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Optional


def utc_now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_snapshot(base_url: str, cron_secret: str):
    url = base_url.rstrip("/") + "/api/admin/monitor/nidhi/run"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {cron_secret}",
            "Accept": "application/json",
            "User-Agent": "fusmle-nidhi-monitor/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def build_alert_message(snapshot: dict) -> Optional[str]:
    sessions = snapshot.get("activeSessions") or []
    flagged = [
        s
        for s in sessions
        if s.get("actionNeeded") and (s.get("mode") or "") == "test3"
    ]
    if not flagged:
        return None
    target = flagged[0]
    if not target:
        return "Nidhi monitor flagged attention needed."
    latest_issue = target.get("latestIssue") or {}
    issue_type = (
        latest_issue.get("eventType")
        or target.get("latestTelemetryEventType")
        or "issue"
    )
    mode = target.get("label") or target.get("mode") or "exam"
    qid = target.get("latestQuestionId") or "unknown question"
    return f"{mode}: {issue_type} on {qid} (session {target.get('sessionId')})"


def send_notification(title: str, message: str):
    script = (
        f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    )
    subprocess.run(["/usr/bin/osascript", "-e", script], check=False)


def ensure_parent(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def write_artifacts(output_dir: pathlib.Path, snapshot: dict):
    ensure_parent(output_dir / "placeholder")
    latest_path = output_dir / "nidhi_monitor_latest.json"
    history_path = output_dir / "nidhi_monitor_live.jsonl"
    latest_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Poll the live Nidhi monitor endpoint and persist snapshots."
    )
    parser.add_argument("--base-url", default="https://uworld-api-deploy.vercel.app")
    parser.add_argument("--cron-secret", required=True)
    parser.add_argument("--output-dir", default="artifacts/evals")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output_dir)

    try:
        snapshot = fetch_snapshot(args.base_url, args.cron_secret)
        snapshot["polledAt"] = utc_now_iso()
        write_artifacts(output_dir, snapshot)
        alert = build_alert_message(snapshot)
        if args.notify and alert:
            send_notification("FUSMLE Nidhi monitor", alert)
        summary = {
            "ok": snapshot.get("ok", False),
            "email": snapshot.get("email"),
            "activeSessions": len(snapshot.get("activeSessions") or []),
            "actionNeeded": bool(snapshot.get("actionNeeded")),
            "checkedAt": snapshot.get("checkedAt"),
            "polledAt": snapshot.get("polledAt"),
        }
        print(json.dumps(summary, sort_keys=True))
        return 0
    except urllib.error.HTTPError as exc:
        error_payload = {
            "ok": False,
            "polledAt": utc_now_iso(),
            "error": f"HTTP {exc.code}",
            "body": exc.read().decode("utf-8", errors="replace"),
        }
        write_artifacts(output_dir, error_payload)
        print(json.dumps(error_payload, sort_keys=True), file=sys.stderr)
        if args.notify:
            send_notification(
                "FUSMLE Nidhi monitor", f"Monitor HTTP failure: {exc.code}"
            )
        return 1
    except Exception as exc:  # pragma: no cover - operational guardrail
        error_payload = {
            "ok": False,
            "polledAt": utc_now_iso(),
            "error": type(exc).__name__,
            "detail": str(exc),
        }
        write_artifacts(output_dir, error_payload)
        print(json.dumps(error_payload, sort_keys=True), file=sys.stderr)
        if args.notify:
            send_notification(
                "FUSMLE Nidhi monitor", f"Monitor failure: {type(exc).__name__}"
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
