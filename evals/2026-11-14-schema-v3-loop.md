# Schema v3 Hardening - 2026-11-14

## Scope

- Work Item: `WI-LE-SCHEMA-V3-20261114`
- Artifact: `A-LE-SCHEMA-V3` version `6`
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
- `F-CONTINUE-CYCLES`: Decisions require unique, strictly increasing cycles;
  a CONTINUE Iteration may remain undecided.
- `F-OPEN-FINDING-CHECKFINDING`: open high/blocking Findings are valid for
  REPAIR/STOP and checked structurally by `check-finding`; only ACCEPT blocks.
- `F-MIGRATION-CLARITY`: the migration record discloses that two role fields
  predated the version-only rewrite; 12 roleless Verification IDs are an
  explicit legacy allowlist.
- `F-LEGACY-ROLE-BOUNDARY`: roleless Verifications are rejected unless the frozen
  migration entry applies; Producer roles never satisfy Verifier.
- `F-LEGACY-ALLOWLIST-BYPASS`: the editable Work Item allowlist was removed;
  roleless evidence now requires the frozen migration entry and exact 29-record
  digest.
- `F-MIGRATION-DIGEST`: `migrations/v2-to-v3.json` binds the available history
  to SHA-256 `db0609f79b9d28db3294150ad6b38dd10aeedbb6b2eaf5ff19cbe37cfa656ad9`.

## Verification

- Local suite: `56/56 OK`
- Configured verify: PASS
- Historical migration: 29/29 records v3; `check-records` PASS; 9/9 Finding
  gates PASS
- External Schema engine: 6 valid samples accepted, 6 invalid samples rejected
- Source and both installed CLI copies: identical SHA-256; installed doctors
  and real Codex/Claude checks PASS
- Final PowerShell User Scope backup stamp: `20261114-230608`
- Artifact code head `74e2c59`; cumulative diff blob
  `b125fc80bfb04adcad03858ae51293613c83e6cb` from
  `git diff --binary c02f1f6..74e2c59 | git hash-object --stdin`
- CI run `43608192970`: 5/5 jobs PASS at `74e2c59`, including Rocky Linux 8
  and all Python 3.8/3.12 targets

## Residual Risks

- Literal CentOS 8 is not booted; Rocky Linux 8 is the executed compatible
  target.
- The default GLM provider remains blocked by an upstream 403; the validated
  Claude path is `qwen3.7-plus`.
- The L3 human-approval runtime remains unimplemented and explicitly blocked.
