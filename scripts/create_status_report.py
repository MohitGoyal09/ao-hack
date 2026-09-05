"""Generate the Covenant Certificate project status report.

    python3 scripts/create_status_report.py                      # -> docs/status-report.md
    python3 scripts/create_status_report.py --out /tmp/status.md
    uv run --with python-docx python scripts/create_status_report.py --out docs/status-report.docx

Facts that go stale (commit, migration/route/label/test-file counts, date) are
read from the repository at run time. Prose lives in SECTIONS below; keep it
consistent with docs/agent-handoff.md, which is the source of truth for status.
Markdown needs only the standard library; .docx needs python-docx (not a
project dependency, hence the `uv run --with` form above).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TITLE = "Covenant Certificate Project Status Report"


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def facts() -> dict[str, str]:
    main_py = (REPO / "apps/api/main.py").read_text(encoding="utf-8")
    dirty = _git("status", "--short")
    return {
        "date": dt.date.today().isoformat(),
        "commit": _git("rev-parse", "--short", "HEAD") + (" (uncommitted changes present)" if dirty else ""),
        "migrations": str(len(list((REPO / "apps/api/supabase/migrations").glob("*.sql")))),
        "routes": str(len(re.findall(r"^@app\.(?:get|post|put|patch|delete)\(", main_py, re.M))
                      + main_py.count('path="/ag-ui"')),
        "gold_labels": str(len(list((REPO / "data/gold").glob("*.json")))),
        "test_files": str(len(list((REPO / "apps/api/tests").glob("test_*.py")))),
    }


# Block kinds: ("p", text) | ("bullets", [items]) | ("table", headers, rows)
def sections(f: dict[str, str]) -> list[tuple[str, list]]:
    return [
        ("Current conclusion", [
            ("p", "The project has a working, tested hackathon build: deterministic covenant "
                  "calculation with fail-closed review policy, Postgres-backed revisions and "
                  "approvals, authenticated immutable document intake, a fenced job worker with a "
                  "case pipeline, and a review workbench UI. It is a reviewed draft generator, not a "
                  "signing tool, and it is not production ready: durable interrupt/resume, event "
                  "replay, live model proof and a holdout evaluation set are still open."),
        ]),
        ("Repository facts (read at generation time)", [
            ("table", ["Fact", "Value"], [
                ["Generated", f["date"]],
                ["Commit", f["commit"]],
                ["SQL migrations in apps/api/supabase/migrations", f["migrations"]],
                ["HTTP routes in apps/api/main.py (incl. /ag-ui)", f["routes"]],
                ["Reviewed extraction-only gold labels in data/gold", f["gold_labels"]],
                ["Backend test modules in apps/api/tests", f["test_files"]],
                ["Backend test result", "run `cd apps/api && uv run python -m unittest discover -s tests`; the suite prints its own count"],
            ]),
        ]),
        ("Implemented", [
            ("bullets", [
                "Typed Decimal calculator, fail-closed policy (missing facts, unclear precedence, missing proof, reviewer identity, period mismatch), hash-chained trace, nine-node LangGraph.",
                "Aon term-loan PDF and 10-K extraction with page/section citations; everything else returns unsupported or needs_ocr and waits for review.",
                "Revisions, impact, stale-command 409s, idempotency and officer approval locked to exact ratio/threshold/comparator/inputs/package hash; Postgres repository when DATABASE_URL is set, explicit memory mode otherwise.",
                "Authenticated multipart intake: one upload = one immutable hashed object, document version, case revision, domain event and queued job.",
                "Durable job queue (lease, heartbeat, retry, cancel, fencing) and worker + case pipeline persisting rules, facts and artifacts per revision.",
                "Fail-closed durability readiness (/health/live, /health/ready); LangGraph checkpoint tables as a tracked migration.",
                "Next.js workbench (/cases/[id]): sign-in, upload, job timeline, review inbox, revisions/impact, officer approval, download; CopilotKit chat over AG-UI.",  # VERIFY: Agent C landed
                "Ten reviewed extraction-only gold labels with dataset-gate tests; no label claims a verdict.",
            ]),
        ]),
        ("Remaining work", [
            ("bullets", [
                "Durable LangGraph interrupt/resume for human review (Phase 5).",
                "Observed live model tool-calling run (NVIDIA NIM or Gemini via LiteLLM); today the offline deterministic graph is what runs without a key.",  # VERIFY before submission
                "Event outbox and AG-UI snapshot/replay; the UI polls today (Phase 6).",
                "Holdout agreement family and versioned accuracy metrics (Phase 8).",
                "Marked PDF workpaper export, security triage, deployment runbooks (Phase 9).",
                "Case-creation API and a user/organization seed script; Neatlogs exercised with a real key.",
            ]),
        ]),
        ("Constraints", [
            ("p", "Live verification is limited to what the hosted Supabase audit and the opt-in "
                  "TEST_DATABASE_URL integration test cover. The report does not claim live model "
                  "calls, Neatlogs traces, user validation or a real-issuer compliance result. "
                  "Server credentials stay in ignored .env files or a secret manager."),
        ]),
    ]


def render_markdown(f: dict[str, str]) -> str:
    out = [f"# {TITLE}", "", f"Status as of {f['date']}. Generated by `scripts/create_status_report.py`.", ""]
    for heading, blocks in sections(f):
        out += [f"## {heading}", ""]
        for block in blocks:
            if block[0] == "p":
                out += [block[1], ""]
            elif block[0] == "bullets":
                out += [f"- {item}" for item in block[1]] + [""]
            else:
                _, headers, rows = block
                out.append("| " + " | ".join(headers) + " |")
                out.append("|" + "---|" * len(headers))
                out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows] + [""]
    return "\n".join(out)


def render_docx(f: dict[str, str], out: Path) -> None:
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
    except ImportError:
        sys.exit("python-docx is not installed. Run:\n"
                 "  uv run --with python-docx python scripts/create_status_report.py --out "
                 f"{out}\nor drop the .docx suffix to write Markdown.")
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10)
    doc.add_heading(TITLE, level=0)
    sub = doc.add_paragraph().add_run(f"Status as of {f['date']}")
    sub.bold = True
    sub.font.color.rgb = RGBColor(75, 85, 99)
    for heading, blocks in sections(f):
        doc.add_heading(heading, level=1)
        for block in blocks:
            if block[0] == "p":
                doc.add_paragraph(block[1])
            elif block[0] == "bullets":
                for item in block[1]:
                    doc.add_paragraph(item, style="List Bullet")
            else:
                _, headers, rows = block
                table = doc.add_table(rows=1, cols=len(headers))
                table.style = "Table Grid"
                for idx, header in enumerate(headers):
                    cell = table.rows[0].cells[idx]
                    cell.text = header
                    cell.paragraphs[0].runs[0].font.bold = True
                for row in rows:
                    for idx, value in enumerate(table.add_row().cells):
                        value.text = str(row[idx])
    doc.core_properties.title = TITLE
    doc.core_properties.author = "Covenant Certificate Team"
    doc.save(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "status-report.md",
                        help="output path; .docx needs python-docx, anything else is Markdown")
    out = parser.parse_args().out
    f = facts()
    if out.suffix.lower() == ".docx":
        render_docx(f, out)
    else:
        out.write_text(render_markdown(f), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
