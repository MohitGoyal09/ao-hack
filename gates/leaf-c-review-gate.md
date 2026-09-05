# Gates: Leaf C — durable review gate

Scope: `src/review_gate.py`, `tests/test_review_gate.py` only.

- [ ] C1: pause on interrupt, resume with matching decision, reject stale/mismatched
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests -p "test_review_gate.py" -v 2>&1 | tail -4
  EXPECT: OK
  EVIDENCE: pending

- [ ] C2: restart proof against Postgres (new graph object, same DB, resumes)
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres uv run python -m unittest discover -s tests -p "test_review_gate.py" 2>&1 | tail -3
  EXPECT: OK
  EVIDENCE: pending

- [ ] C3: full suite still green
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests 2>&1 | tail -3
  EXPECT: OK
  EVIDENCE: pending
