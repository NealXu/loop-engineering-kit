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
- Review findings and a decision record.

## Acceptance

- Requested behavior and edge cases are covered.
- Required build, test, and compatibility checks have executed evidence.
- No open `blocking`/`high` findings remain.
- Unrelated work is preserved and scope changes are disclosed.
- Security, data-loss, accessibility, and migration risks are addressed when
  relevant.

## Challenge Focus

Requirements gaps, boundary conditions, failure recovery, backwards
compatibility, hidden coupling, and whether an existing implementation or
standard-library feature should have been reused.
