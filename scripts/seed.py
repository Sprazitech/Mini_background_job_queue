import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx


REQUIRED_ENV_VARS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
LOCAL_FALLBACK_URL = "http://localhost:5432"


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_jobs() -> list[dict]:
    now = datetime.now(timezone.utc)
    rows: list[dict] = []

    queued_jobs = [
        {
            "type": "send_email",
            "payload": {"to": "alice@example.com", "subject": "Welcome"},
            "status": "queued",
            "attempts": 0,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now + timedelta(minutes=1)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(minutes=10)),
            "updated_at": iso_utc(now - timedelta(minutes=2)),
            "started_at": None,
            "finished_at": None,
        },
        {
            "type": "generate_report",
            "payload": {"report_id": "rep-1001", "format": "csv"},
            "status": "queued",
            "attempts": 0,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now + timedelta(minutes=2)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(minutes=8)),
            "updated_at": iso_utc(now - timedelta(minutes=1)),
            "started_at": None,
            "finished_at": None,
        },
        {
            "type": "send_email",
            "payload": {"to": "bob@example.com", "subject": "Invoice"},
            "status": "queued",
            "attempts": 1,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now + timedelta(minutes=3)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(minutes=7)),
            "updated_at": iso_utc(now - timedelta(minutes=1)),
            "started_at": None,
            "finished_at": None,
        },
        {
            "type": "generate_report",
            "payload": {"report_id": "rep-1002", "format": "json"},
            "status": "queued",
            "attempts": 0,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now + timedelta(minutes=4)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(minutes=6)),
            "updated_at": iso_utc(now - timedelta(minutes=2)),
            "started_at": None,
            "finished_at": None,
        },
        {
            "type": "send_email",
            "payload": {"to": "carol@example.com", "subject": "Password reset"},
            "status": "queued",
            "attempts": 0,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now + timedelta(minutes=5)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(minutes=5)),
            "updated_at": iso_utc(now - timedelta(minutes=3)),
            "started_at": None,
            "finished_at": None,
        },
    ]

    success_jobs = [
        {
            "type": "send_email",
            "payload": {"to": "dave@example.com", "subject": "Receipt"},
            "status": "success",
            "attempts": 1,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now - timedelta(minutes=30)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(days=1)),
            "updated_at": iso_utc(now - timedelta(hours=3)),
            "started_at": iso_utc(now - timedelta(hours=4)),
            "finished_at": iso_utc(now - timedelta(hours=3)),
        },
        {
            "type": "generate_report",
            "payload": {"report_id": "rep-2001", "format": "csv"},
            "status": "success",
            "attempts": 2,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now - timedelta(minutes=25)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(days=2)),
            "updated_at": iso_utc(now - timedelta(hours=5)),
            "started_at": iso_utc(now - timedelta(hours=6)),
            "finished_at": iso_utc(now - timedelta(hours=5)),
        },
        {
            "type": "send_email",
            "payload": {"to": "erin@example.com", "subject": "Order shipped"},
            "status": "success",
            "attempts": 1,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now - timedelta(minutes=20)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(days=3)),
            "updated_at": iso_utc(now - timedelta(hours=2)),
            "started_at": iso_utc(now - timedelta(hours=3)),
            "finished_at": iso_utc(now - timedelta(hours=2)),
        },
        {
            "type": "generate_report",
            "payload": {"report_id": "rep-2002", "format": "json"},
            "status": "success",
            "attempts": 1,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now - timedelta(minutes=15)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(days=4)),
            "updated_at": iso_utc(now - timedelta(hours=1)),
            "started_at": iso_utc(now - timedelta(hours=2)),
            "finished_at": iso_utc(now - timedelta(hours=1)),
        },
    ]

    failed_jobs = [
        {
            "type": "send_email",
            "payload": {"force_fail": True, "to": "frank@example.com", "subject": "Alert"},
            "status": "failed",
            "attempts": 3,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now - timedelta(minutes=45)),
            "last_error": "SMTP timeout after retries",
            "created_at": iso_utc(now - timedelta(days=2)),
            "updated_at": iso_utc(now - timedelta(hours=2)),
            "started_at": iso_utc(now - timedelta(hours=3)),
            "finished_at": iso_utc(now - timedelta(hours=2)),
        },
        {
            "type": "generate_report",
            "payload": {"report_id": "rep-3001", "format": "csv"},
            "status": "failed",
            "attempts": 2,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now - timedelta(minutes=30)),
            "last_error": "Report generation failed due to invalid dataset",
            "created_at": iso_utc(now - timedelta(days=3)),
            "updated_at": iso_utc(now - timedelta(hours=4)),
            "started_at": iso_utc(now - timedelta(hours=5)),
            "finished_at": iso_utc(now - timedelta(hours=4)),
        },
        {
            "type": "send_email",
            "payload": {"to": "grace@example.com", "subject": "Reminder"},
            "status": "failed",
            "attempts": 3,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now - timedelta(minutes=10)),
            "last_error": "HTTP 500 from provider",
            "created_at": iso_utc(now - timedelta(days=1)),
            "updated_at": iso_utc(now - timedelta(minutes=15)),
            "started_at": iso_utc(now - timedelta(minutes=30)),
            "finished_at": iso_utc(now - timedelta(minutes=15)),
        },
    ]

    running_jobs = [
        {
            "type": "send_email",
            "payload": {"to": "heidi@example.com", "subject": "Delivery status"},
            "status": "running",
            "attempts": 1,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now + timedelta(minutes=10)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(minutes=20)),
            "updated_at": iso_utc(now - timedelta(minutes=1)),
            "started_at": iso_utc(now - timedelta(minutes=5)),
            "finished_at": None,
        },
        {
            "type": "generate_report",
            "payload": {"report_id": "rep-4001", "format": "xlsx"},
            "status": "running",
            "attempts": 2,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now + timedelta(minutes=15)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(minutes=25)),
            "updated_at": iso_utc(now - timedelta(minutes=2)),
            "started_at": iso_utc(now - timedelta(minutes=8)),
            "finished_at": None,
        },
        {
            "type": "send_email",
            "payload": {"to": "ivan@example.com", "subject": "Follow-up"},
            "status": "running",
            "attempts": 1,
            "max_retries": 3,
            "next_attempt_at": iso_utc(now + timedelta(minutes=20)),
            "last_error": None,
            "created_at": iso_utc(now - timedelta(minutes=30)),
            "updated_at": iso_utc(now - timedelta(minutes=3)),
            "started_at": iso_utc(now - timedelta(minutes=9)),
            "finished_at": None,
        },
    ]

    return queued_jobs + success_jobs + failed_jobs + running_jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the Supabase jobs table")
    parser.add_argument("--confirm", action="store_true", help="Required confirmation flag")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.confirm:
        print("Warning: --confirm flag required to seed data.")
        raise SystemExit(1)

    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        raise SystemExit(1)

    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    rows = build_jobs()

    try:
        response = httpx.post(
            f"{supabase_url}/rest/v1/jobs",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=rows,
            timeout=30.0,
        )
        response.raise_for_status()
    except Exception as exc:
        print(
            "Could not seed the database.\n"
            f"Supabase URL: {supabase_url}\n"
            "Check that the project is reachable and that the jobs table exists.\n"
            "If you are testing locally, start Postgres and set DATABASE_URL before seeding.\n"
            f"Original error: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    print("Seeded 15 jobs")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Seed interrupted", file=sys.stderr)
        raise SystemExit(1)
