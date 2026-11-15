# Software Development Pack

## Role Binding

| Generic role | Domain role |
|---|---|
| Producer | Implementer |
| Verifier | Test or build verifier |
| Reviewer | Independent code reviewer |
| Challenger | Requirements and design challenger |
| Arbiter | Controller or human approver |

## Required Artifacts

- Code change or patch with versioned file list.
- Tests or an assert-based self-check for non-trivial logic.
- Verification report with exact commands, exit codes, and status.
- A verification skill based on `verification-skill.md` when a browser, GUI, or
  multi-step workflow needs repeatable execution and evidence.
- Review findings and a decision record.

## Acceptance

- Requested behavior and edge cases are covered.
- Required build, test, and compatibility checks have executed evidence.
- Numeric or monetary changes include an aggregate or boundary check; a visible
  happy-path test alone is insufficient.
- The selected control tier was followed: L0 is direct; L1 has verification;
  L2 has independent review; L3 has challenge and human approval before
  irreversible actions. L3 approval is a canonical approval record for the
  final Artifact version.
- No open `blocking`/`high` findings remain.
- Unrelated work is preserved and scope changes are disclosed.
- Security, data-loss, accessibility, and migration risks are addressed when
  relevant.
- A repeated failure fingerprint without a new artifact version is not hidden
  by consuming the remaining repair budget.
- Every Work Item acceptance `criterion_id` has at least one executed
  Verification with matching `criterion_ids`; no criterion is accepted on
  prose alone.
- A repeated finding and a closed `high` or `blocking` finding (`resolved` or
  `not_reproducible`) records one `prevention` choice: `structure`,
  `automatic_check`, `skill_rule`, or `human_review`. Prefer them in that
  order. Every kind requires stable `regression_verification_ids` that resolve
  to PASS evidence; every non-`structure` choice also records
  `fallback_reason`. Mark recurrence with `recurrence_of`; a recurrence cannot
  omit prevention in any status.

## Challenge Focus

Requirements gaps, boundary conditions, failure recovery, backwards
compatibility, hidden coupling, and whether an existing implementation or
standard-library feature should have been reused. When the same correction is
repeated, challenge why the project changed only the artifact instead of making
the bad state harder to create.
