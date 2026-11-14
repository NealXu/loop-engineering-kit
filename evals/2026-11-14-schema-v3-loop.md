# Schema v3 Hardening - 2026-11-14

## Scope

- Work Item: `WI-LE-SCHEMA-V3-20261114`
- Artifact: `A-LE-SCHEMA-V3` version `3`
- Base: `c02f1f6`; previous head: `7cf0af6`
- Repair budget: `3`

This follow-up closes the incompatible v2 schema change and the remaining
Reviewer-evidence gate.

## Repairs

- `F-SCHEMA-VERSION`: all six canonical Schemas are explicit v3 records with
  migration documentation for v1/v2.
- `F-SCHEMA-KEYWORDS`: the built-in validator now covers `boolean`, `not`,
  `anyOf`, and `maxItems`, matching the keywords used by the shipped Schemas.
- `F-REVIEW-EVIDENCE`: L2/L3 ACCEPT now requires a referenced final-version
  Reviewer Verification with `status: PASS`. Reviewer Findings and failed,
  blocked, not-run, or stale Verifications cannot substitute.
- `F-ARTIFACT-PROVENANCE`: the previous terminal Artifact v2 remains frozen;
  this work uses a new Work Item and Artifact so local and CI evidence target
  the actual current content.
- `F-VERIFIER-ROLE`: every accepted criterion needs final-version Verifier
  evidence; a Producer Verification cannot self-certify the gate.
- `F-STOP-OPEN-QUESTIONS`: a final STOP may preserve unresolved questions;
  only ACCEPT rejects them.
- `F-DIFF-HASH`: provenance uses Git's raw diff blob instead of PowerShell's
  newline-normalized text.
- `F-STALE-TEST-RECORDS`: each record rewrite clears stale JSON files, and a
  removed Finding is asserted absent before later checks.
- `F-STOP-TEST-PATH`: the STOP fixture now includes a resolved high Finding
  with prevention, so it exercises the original regression path.

## Verification

- Local suite: `56/56 OK`
- Configured verify: PASS
- Historical migration: 29/29 records v3; `check-records` PASS; 9/9 Finding
  gates PASS
- External Schema engine: 6 valid samples accepted, 6 invalid samples rejected
- Source and both installed CLI copies: identical SHA-256; installed doctors
  and real Codex/Claude checks PASS
- Final PowerShell User Scope backup stamp: `20261114-220743`
- Artifact code head `c7349a0`; cumulative diff blob
  `0e47126ee68c10d8af3e7333dc22a0cec5da780d` from
  `git diff --binary c02f1f6..c7349a0 | git hash-object --stdin`
- CI run `43604359219`: 5/5 jobs PASS at `c7349a0`, including Rocky Linux 8
  and all Python 3.8/3.12 targets

## Residual Risks

- Literal CentOS 8 is not booted; Rocky Linux 8 is the executed compatible
  target.
- The default GLM provider remains blocked by an upstream 403; the validated
  Claude path is `qwen3.7-plus`.
- The L3 human-approval runtime remains unimplemented and explicitly blocked.
