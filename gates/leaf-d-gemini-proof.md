# Gates: Leaf D — live Gemini proof (credential-gated)

Scope: `tests/test_gemini_proof.py` only. No source changes.

- [ ] D1: structured-output + tool-call contract verified live, or clean skip with reason
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests -p "test_gemini_proof.py" -v 2>&1 | tail -6
  EXPECT: OK
  EVIDENCE: pending

- [ ] D2: full suite still green
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests 2>&1 | tail -3
  EXPECT: OK
  EVIDENCE: pending
