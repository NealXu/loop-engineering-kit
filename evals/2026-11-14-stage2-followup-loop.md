# Stage 2 Follow-Up - 2026-11-14

## Scope

- Work Item: `WI-LE-STAGE2-FOLLOWUP-20261114`
- Artifact: `A-LE-STAGE2-FOLLOWUP` version `2`
- Base: `c02f1f6`
- Repair budget: `3`

This follow-up starts after the previous Stage 2 Work Item exhausted its three
artifact repairs. It preserves the previous v4 snapshot instead of rewriting
its history. The later Schema v3 hardening is tracked separately in
`2026-11-14-schema-v3-loop.md`.

## Resolved Findings

- `F-DECISION-HISTORY`: multiple Decisions are ordered by `cycle`; exactly one
  final ACCEPT must target the final Artifact version.
- `F-EVIDENCE-REFS`: Decision `evidence_refs` contain stable Finding or
  Verification IDs; prose and external locations use `evidence_notes`.
  Closed high/blocking/recurring Findings resolve their prevention evidence
  through `check-records`.
- `F-TEST-COUNT`: current evidence uses the exact 55-test count.
- `F-REPAIR-LINKAGE`: REPAIR state transitions must match whether the same-cycle
  Iteration produces a new Artifact version.
- `F-OPEN-RECURRENCE`: prevention and recurrence evidence resolves in every
  Finding status.
- `F-ID-COLLISION`: stable IDs are unique across non-Artifact record types.
- `F-TERMINAL`: only one terminal ACCEPT/STOP/ESCALATE is allowed and it must
  be last; Iteration.result matches the same-cycle Decision.
- `F-CONTROL-TIER`: Work Item control_tier is explicit and cannot be lower than
  the route selected from risk and file count.
- `F-UNDECIDED`: non-CONTINUE Iterations require a same-cycle Decision.
- `F-REPAIR-VERSION`: artifact REPAIR names the pre-repair input version.
- `F-RISK-ID` and `F-MALFORMED-KIND`: dangling risk references and non-string
  record kinds fail with structured diagnostics.

## Verification

- Local suite: `56/56 OK`
- Configured verify: PASS
- Canonical `check-records`: PASS
- Closed Finding gates: PASS
- Source and both installed doctors: PASS
- Rocky Linux 8: current applicable suite PASS with the expected Windows-only
  PowerShell skip
- Final authorization run `43599436863`: five jobs PASS at `7cf0af6`,
  including Rocky Linux 8 and all Python 3.8/3.12 targets.

## Residual Risks

- Literal CentOS 8 was not booted; Rocky Linux 8 is the executed compatible
  target.
- The default GLM provider remains blocked by an upstream 403.
