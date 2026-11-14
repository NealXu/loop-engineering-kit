# Verification Skill Template

Use this template when a software behavior needs repeatable execution, or when
an agent repeatedly verifies the same browser, desktop, API, or multi-step CLI
workflow by hand. Prefer the smallest lint, unit, or integration check that
already proves the behavior; add a skill only for coordination and observable
execution that a single command cannot cover.

## Function Map

List the capabilities from the user's point of view. Use stable feature IDs so
the Work Item, driver, and evidence can refer to the same thing.

| Feature ID | Entry point | User action | Observable success | Primary evidence |
|---|---|---|---|---|
| F-01 | | | | |

## Reusable Driver

- Provide one trusted, non-interactive command with an `argv` array or an
  equivalent host-native configuration.
- Keep credentials out of the command and evidence.
- Return a non-zero exit code on failure and print the failed feature ID.
- Reuse the driver for success, boundary, and recovery scenarios instead of
  teaching the agent a new manual sequence for every run.
- When the existing `.loop-engineering.json` `verify` command can run it, use
  that path instead of adding a second runner.

## Scenarios

- Happy path: one representative successful user flow.
- Boundary: empty, maximum, invalid, concurrent, or domain-specific edge case.
- Failure and recovery: prove the expected error is visible and the workflow
  can recover without data loss.
- Add randomized or property-based exploration only when the risk justifies
  its cost; record the seed or input set.

## Evidence

Record the artifact ID/version, every covered `criterion_id`, exact command,
exit code, duration, evidence paths, and the `limitations` array. A passing
claim needs executed evidence; `BLOCKED` and `NOT_RUN` remain non-passing.
Screenshots, video, traces, and reports are evidence artifacts, not
replacements for the canonical Verification record.

When the Verification is the regression evidence for a Finding, include
`finding_id` equal to that Finding's stable ID and verify it with
`check-finding`.

## Stop Conditions

- A required command fails, times out, or cannot reproduce the claimed state.
- Expected evidence is missing, stale for the artifact version, or no longer
  matches the current function map.
- The driver mutates data outside the declared test scope.
- The same failure fingerprint repeats after the function map or driver was
  corrected; stop and diagnose instead of rerunning blindly.

## Human Gates

Use human approval before destructive, production-impacting, credential-related,
payment, publication, or other irreversible actions. Stop for the user's
decision when the acceptance semantics are ambiguous; a Reviewer or visual
check cannot choose the intended product behavior.
