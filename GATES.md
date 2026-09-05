# Gates: Phase 5 — tools and durable human review

Scope: Schemas + recording, case tools, review gate, live Gemini proof,
then review, graph wiring, verify, ship. Leaf gates in gates/leaf-*.md.

- [ ] G1: leaf A gates met (schemas + recording + migration)
  EVIDENCE: pending (see gates/leaf-a-model-calls.md)

- [ ] G2: leaf B gates met (case-state tools)
  EVIDENCE: pending (see gates/leaf-b-case-tools.md)

- [ ] G3: leaf C gates met (durable review gate)
  EVIDENCE: pending (see gates/leaf-c-review-gate.md)

- [ ] G4: leaf D gates met (live proof or clean credential skip)
  EVIDENCE: pending (see gates/leaf-d-gemini-proof.md)

- [ ] G5: review agent fixed all found bugs; new tools wired into agent graph
  EVIDENCE: pending

- [ ] G6: parent re-run — full suite offline
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && uv run python -m unittest discover -s tests 2>&1 | tail -3
  EXPECT: OK
  EVIDENCE: pending

- [ ] G7: parent re-run — full suite with integration DB
  CHECK: cd /Users/mohit/Code/ao-hack/apps/api && TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres uv run python -m unittest discover -s tests 2>&1 | tail -3
  EXPECT: OK
  EVIDENCE: pending

- [ ] G8: frontend build passes; local lint clean; diff clean
  CHECK: cd /Users/mohit/Code/ao-hack/apps/web && npm run build 2>&1 | grep Compiled
  EXPECT: Compiled successfully
  EVIDENCE: pending
