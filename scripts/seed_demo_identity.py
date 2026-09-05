"""Seed (or verify) the hosted demo identity: one org, one officer, optional reviewer.

    cd apps/api && uv run python ../../scripts/seed_demo_identity.py          # create-if-missing, then verify
    cd apps/api && uv run python ../../scripts/seed_demo_identity.py --check  # read-only verification only

Reads the git-ignored root .env. Additive and idempotent: users are created only
when absent (Auth admin API, email pre-confirmed, app_metadata.role set); the
org and membership rows are upserted (membership role is the only thing ever
updated). Prints identifiers and booleans only, never passwords or tokens.

Env: SUPABASE_URL, SUPABASE_SECRET_KEY, SUPABASE_PUBLISHABLE_KEY, DATABASE_URL,
DEMO_OFFICER_EMAIL, DEMO_OFFICER_PASSWORD; optional DEMO_REVIEWER_EMAIL +
DEMO_REVIEWER_PASSWORD (role treasury_reviewer, for the 403-for-non-officer
beat); DEMO_ORG_ID = org slug (default demo-treasury; an existing org UUID works).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")

REQUIRED = ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_PUBLISHABLE_KEY",
            "DATABASE_URL", "DEMO_OFFICER_EMAIL", "DEMO_OFFICER_PASSWORD")


def env() -> dict[str, str]:
    missing = [k for k in REQUIRED if not os.getenv(k, "").strip()]
    if os.getenv("DEMO_REVIEWER_EMAIL") and not os.getenv("DEMO_REVIEWER_PASSWORD"):
        missing.append("DEMO_REVIEWER_PASSWORD")
    if missing:
        sys.exit(f"missing env (set them in {REPO / '.env'}): {', '.join(missing)}")
    return {k: os.environ[k].strip() for k in REQUIRED}


def users() -> list[tuple[str, str, str]]:
    out = [(os.environ["DEMO_OFFICER_EMAIL"], os.environ["DEMO_OFFICER_PASSWORD"], "officer")]
    if os.getenv("DEMO_REVIEWER_EMAIL"):
        out.append((os.environ["DEMO_REVIEWER_EMAIL"], os.environ["DEMO_REVIEWER_PASSWORD"],
                    "treasury_reviewer"))
    return out


def auth(path: str, body: dict | None = None, key: str | None = None) -> tuple[int, dict]:
    """GoTrue call; admin routes use the secret key, the token route the publishable key."""
    key = key or os.environ["SUPABASE_SECRET_KEY"]
    req = urllib.request.Request(os.environ["SUPABASE_URL"].rstrip("/") + path,
                                 method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def find_user(cur, email: str) -> tuple[str, str | None] | None:
    cur.execute("select id, raw_app_meta_data->>'role' from auth.users where email = %s", (email,))
    row = cur.fetchone()
    return (str(row[0]), row[1]) if row else None


def find_org(cur, ref: str) -> tuple[str, str] | None:
    cur.execute("select id, slug from public.organizations where slug = %s or id::text = %s",
                (ref, ref))
    row = cur.fetchone()
    return (str(row[0]), row[1]) if row else None


def seed(conn) -> None:
    org_ref = os.getenv("DEMO_ORG_ID", "demo-treasury").strip() or "demo-treasury"
    with conn.cursor() as cur:
        ids: dict[str, str] = {}
        for email, password, role in users():
            found = find_user(cur, email)
            if found:
                ids[email] = found[0]
                print(f"user found:   {email} id={found[0]} app_role={found[1]}")
                continue
            status, user = auth("/auth/v1/admin/users", {
                "email": email, "password": password, "email_confirm": True,
                "app_metadata": {"role": role},
                "user_metadata": {"name": f"Demo {role.replace('_', ' ').title()}"},
            })
            if status not in (200, 201):
                sys.exit(f"auth admin create failed for {email}: HTTP {status} {user}")
            ids[email] = user["id"]
            print(f"user created: {email} id={user['id']} app_role={role}")

        org = find_org(cur, org_ref)
        if org:
            print(f"org found:    slug={org[1]} id={org[0]}")
        else:
            officer_id = ids[os.environ["DEMO_OFFICER_EMAIL"]]
            cur.execute("insert into public.organizations (name, slug, created_by)"
                        " values (%s, %s, %s) returning id, slug",
                        (org_ref.replace("-", " ").title(), org_ref, officer_id))
            row = cur.fetchone()
            org = (str(row[0]), row[1])
            print(f"org created:  slug={org[1]} id={org[0]}")

        for email, _, role in users():
            cur.execute("select role from public.organization_members"
                        " where organization_id = %s and user_id = %s", (org[0], ids[email]))
            row = cur.fetchone()
            if row and row[0] == role:
                print(f"member found: {email} role={role}")
                continue
            cur.execute("insert into public.organization_members (organization_id, user_id, role)"
                        " values (%s, %s, %s)"
                        " on conflict (organization_id, user_id) do update set role = excluded.role",
                        (org[0], ids[email], role))
            print(f"member {'updated' if row else 'created'}: {email} role={role}"
                  + (f" (was {row[0]})" if row else ""))
    conn.commit()


def check(conn) -> bool:
    """Read-only: user exists, membership role, migrations applied, password login works."""
    ok = True
    org_ref = os.getenv("DEMO_ORG_ID", "demo-treasury").strip() or "demo-treasury"
    with conn.cursor() as cur:
        cur.execute("select count(*) from supabase_migrations.schema_migrations")
        applied = cur.fetchone()[0]
        expected = len(list((REPO / "apps/api/supabase/migrations").glob("*.sql")))
        print(f"migrations applied={applied} tracked={expected} ok={applied >= expected}")
        ok &= applied >= expected
        org = find_org(cur, org_ref)
        print(f"org {org_ref}: exists={org is not None}" + (f" id={org[0]}" if org else ""))
        ok &= org is not None
        for email, password, role in users():
            found = find_user(cur, email)
            member = None
            if found and org:
                cur.execute("select role from public.organization_members"
                            " where organization_id = %s and user_id = %s", (org[0], found[0]))
                row = cur.fetchone()
                member = row[0] if row else None
            status, tok = auth("/auth/v1/token?grant_type=password",
                               {"email": email, "password": password},
                               key=os.environ["SUPABASE_PUBLISHABLE_KEY"])
            claim = ((tok.get("user") or {}).get("app_metadata") or {}).get("role")
            good = bool(found) and member == role and status == 200
            ok &= good
            print(f"{role}: exists={found is not None} member_role={member} "
                  f"login_ok={status == 200} role_claim={claim} ok={good}"
                  + (f" id={found[0]}" if found else ""))
    return bool(ok)


def main() -> None:
    env()
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15) as conn:
        if "--check" not in sys.argv:
            seed(conn)
        sys.exit(0 if check(conn) else 1)


if __name__ == "__main__":
    main()
