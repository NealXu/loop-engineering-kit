# Continuous Improvement Workflow

Task iteration repairs the current artifact. Continuous improvement changes the
process itself and therefore needs its own evidence and approval.

1. Aggregate completed run records: rework, failed checks, escaped defects, and
   effective challenges.
2. Identify a repeated pattern and the workflow, role, pack, or check that
   should change.
3. Select the earliest viable prevention:
   1. Change the structure or API so the bad state or workflow cannot recur.
   2. Add the narrowest deterministic check that catches the recurrence.
   3. Update a skill or rule only for judgment that cannot be encoded.
   4. Use human review only for semantics or actions that cannot be automated.
   A repeated pattern is not resolved by repairing only its latest artifact.
4. Write a bounded improvement candidate with expected effect and rollback.
5. Freeze the harness version, model, task sequence, budget, and scoring
   method. Compare the candidate with the current version in fresh sessions.
6. Check both the targeted failure and unrelated/regression cases. A change
   that does not reduce the targeted problem, or adds work elsewhere, is
   removed rather than promoted.
7. Obtain independent review and human approval before publishing a rule
   change.
8. Keep the prior version available and record how to restore it.

An agent may propose an improvement but may not silently promote it into global
rules. Stage 3 implements metrics with `metrics`, version history with
`registry-update`/`registry-list`, and deterministic candidate generation with
`improvements`. Candidate generation stops before review and approval.
