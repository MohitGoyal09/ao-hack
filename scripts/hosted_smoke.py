"""Hosted smoke test: officer login -> /health/ready -> case snapshot [-> upload + worker pass].

    cd apps/api && uv run python ../../scripts/hosted_smoke.py                 # read-only against :8123
    cd apps/api && uv run python ../../scripts/hosted_smoke.py --api http://localhost:8131 --full

Reads the git-ignored root .env for SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and
DEMO_OFFICER_EMAIL/PASSWORD (plus DATABASE_URL/SUPABASE_SECRET_KEY for --full,
which uploads data/raw/pdf-fixtures/aon-credit-agreement.pdf, runs the real
Worker once in-process with the real Supabase storage adapter, and re-reads the
snapshot). When DEMO_REVIEWER_* are set it also proves the reviewer can read the
case (200) but not approve it (403). Prints status codes and counts, no secrets.
Exit code is non-zero when any step fails.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx  # already installed: supabase -> httpx
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")
FIXTURE = REPO / "data/raw/pdf-fixtures/aon-credit-agreement.pdf"


def login(email_key: str, password_key: str) -> httpx.Client | None:
    email, password = os.getenv(email_key, ""), os.getenv(password_key, "")
    if not (email and password):
        return None
    r = httpx.post(f"{os.environ['SUPABASE_URL'].rstrip('/')}/auth/v1/token?grant_type=password",
                   headers={"apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"]},
                   json={"email": email, "password": password}, timeout=30)
    print(f"login {email_key}: HTTP {r.status_code} (token redacted)")
    if r.status_code != 200:
        return None
    return httpx.Client(base_url=ARGS.api, timeout=120,
                        headers={"Authorization": f"Bearer {r.json()['access_token']}"})


def snapshot(c: httpx.Client, label: str) -> dict:
    r = c.get(f"/api/cases/{ARGS.case}/snapshot")
    s = r.json() if r.status_code == 200 else {}
    print(f"snapshot {label}: HTTP {r.status_code} head={(s.get('revision') or {}).get('revision_id')} "
          f"run_state={s.get('run_state')} package_state={s.get('package_state')} "
          f"artifacts={len(s.get('artifacts') or {})} review_issues={len(s.get('review_issues') or [])} "
          f"open={s.get('open_review_issues')} approvals={len(s.get('approvals') or [])}")
    if r.status_code != 200:
        print("  detail:", r.text[:300])
        sys.exit(1)
    return s


def run_worker_once(job_id: str, c: httpx.Client) -> str:
    """Same wiring as src.platform.worker.main(), one lease instead of run_forever."""
    sys.path.insert(0, str(REPO / "apps/api"))
    from src.covenant.pipeline import CasePipeline
    from src.platform.jobqueue import configured_database_url, job_store_from_env
    from src.platform.storage import storage_adapter_from_env
    from src.platform.supabase import SupabasePlatform
    from src.platform.worker import Worker

    platform = SupabasePlatform.from_env()
    if not platform.enabled or configured_database_url() is None:
        sys.exit("--full needs SUPABASE_URL, SUPABASE_SECRET_KEY and DATABASE_URL in .env")
    storage = storage_adapter_from_env(platform._client, platform._bucket)  # noqa: SLF001
    worker = Worker(job_store_from_env(), CasePipeline(configured_database_url(), storage),
                    worker_id="hosted-smoke", lease_seconds=60)
    outcome = worker.run_once()
    print(f"worker run_once: {outcome}")
    # ponytail: 'idle' means another worker (compose/terminal) leased the job first; poll it instead.
    deadline = time.time() + 90
    while True:
        job = next((j for j in c.get(f"/api/cases/{ARGS.case}/jobs").json() if j["job_id"] == job_id), {})
        state = job.get("state")
        if state in ("completed", "failed", "cancelled") or time.time() > deadline:
            print(f"job {job_id}: state={state} attempts={job.get('attempt_count')} last_error={job.get('last_error')}")
            return str(state)
        time.sleep(2)


def main() -> int:
    for k in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "DEMO_OFFICER_EMAIL", "DEMO_OFFICER_PASSWORD"):
        if not os.getenv(k):
            sys.exit(f"missing env {k} (see docs/hosted-setup.md)")
    officer = login("DEMO_OFFICER_EMAIL", "DEMO_OFFICER_PASSWORD")
    if officer is None:
        return 1
    ready = officer.get("/health/ready")
    d = ready.json().get("durability", {})
    print(f"ready: HTTP {ready.status_code} mode={d.get('mode')} status={d.get('status')}")
    if ready.status_code != 200:
        print("  detail:", ready.text[:300])
        return 1
    snapshot(officer, "before")
    failed = 0

    reviewer = login("DEMO_REVIEWER_EMAIL", "DEMO_REVIEWER_PASSWORD")
    if reviewer is not None:
        r_snap = reviewer.get(f"/api/cases/{ARGS.case}/snapshot").status_code
        r_appr = reviewer.post(f"/api/cases/{ARGS.case}/officer-approval", json={}).status_code
        print(f"reviewer: snapshot HTTP {r_snap} (want 200), officer-approval HTTP {r_appr} (want 403)")
        failed += (r_snap, r_appr) != (200, 403)

    if ARGS.full:
        with FIXTURE.open("rb") as fh:
            up = officer.post(f"/api/cases/{ARGS.case}/documents",
                              files={"file": (FIXTURE.name, fh, "application/pdf")},
                              data={"document_role": "credit_agreement", "title": "AON credit agreement (hosted smoke)"})
        body = up.json() if up.status_code == 200 else {}
        print(f"upload: HTTP {up.status_code} document_id={body.get('document_id')} "
              f"revision_id={body.get('revision_id')} job_id={body.get('job_id')}")
        if up.status_code != 200:
            print("  detail:", up.text[:300])
            return 1
        state = run_worker_once(body["job_id"], officer)
        after = snapshot(officer, "after")
        print("  artifact types:", sorted((after.get("artifacts") or {}).keys()))
        failed += state != "completed"
    print("SMOKE", "FAIL" if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--api", default="http://localhost:8123")
    p.add_argument("--case", default="aurora-net-leverage")
    p.add_argument("--full", action="store_true", help="upload fixture, run the worker once, re-read snapshot")
    ARGS = p.parse_args()
    sys.exit(main())
