# Status report generator (`scripts/create_status_report.py`)

Renders a one-page project status report from the repository. Facts that go
stale — commit, number of migrations, routes, gold labels and test modules,
generation date — are read at run time; the prose lives in `SECTIONS` inside
the script and must be kept consistent with `docs/agent-handoff.md`, which is
the source of truth for project status.

## Run

```bash
# Markdown, standard library only -> docs/status-report.md
python3 scripts/create_status_report.py

# anywhere else
python3 scripts/create_status_report.py --out /tmp/status.md

# Word document; python-docx is not a project dependency, so pull it in ad hoc
uv run --with python-docx python scripts/create_status_report.py --out docs/status-report.docx
```

Asking for `.docx` without python-docx installed prints the `uv run --with`
command above and exits non-zero instead of crashing.

## Report content

1. Current conclusion — one paragraph, what works and what is still open.
2. Repository facts — table read from the tree (commit, counts). The test
   result row points at the suite command rather than embedding a number.
3. Implemented / Remaining work — bullet lists.
4. Constraints — what the report does not claim (live model calls, Neatlogs
   traces, user validation, real-issuer verdicts).

## Keeping it current

Edit `sections()` in the script when a phase lands, re-run it, and update the
same facts in `docs/agent-handoff.md`. Do not add counts to the prose; add
them to `facts()` so they are computed.

History: the first version of this script (commit `f63aed1`) wrote a styled
`.docx` to a hard-coded OneDrive path with counts frozen at commit `cbe2599`.
Both were replaced on 2026-09-06.
