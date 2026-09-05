# Gates: Leaf A — schemas + model-call recording

Scope: new migration, `src/model_calls.py`, `tests/test_model_calls.py` only.

- [ ] A1: proposal schemas validate strictly (reject bad amount/comparator/empty rationale)
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests -p "test_model_calls.py" -v 2>&1 | tail -4
  EXPECT: OK
  EVIDENCE: pending

- [ ] A2: recorded calls survive reconstruction with exact cost strings (Postgres)
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres uv run python -m unittest discover -s tests -p "test_model_calls.py" 2>&1 | tail -3
  EXPECT: OK
  EVIDENCE: pending

- [ ] A3: full suite still green
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests 2>&1 | tail -3
  EXPECT: OK
  EVIDENCE: pending
