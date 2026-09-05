# Gates: Leaf B — case-state tools

Scope: `src/case_tools.py`, `tests/test_agent_tools.py` only.

- [ ] B1: all five tools return valid JSON on persisted state; errors as JSON not raises
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests -p "test_agent_tools.py" -v 2>&1 | tail -4
  EXPECT: OK
  EVIDENCE: pending

- [ ] B2: full suite still green
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests 2>&1 | tail -3
  EXPECT: OK
  EVIDENCE: pending
