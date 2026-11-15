# Project Status Ledger

Updated: 2026-11-15

This is the authoritative project-level status ledger. Historical run details
remain in `evals/`; canonical role records remain run-scoped JSON evidence.

## Completed capabilities

| Capability | Status | Entry point / evidence |
|---|---|---|
| L0-L3 routing, repair budgets, role selection | Complete | `loop_engineering/cli.py route` |
| Seven v3 canonical record schemas | Complete | `core/artifact-schema/*.schema.json` |
| Cross-record, ancestry, role, and approval validation | Complete | `check-records`, `check-finding` |
| Safe v1/v2 to v3 migration | Complete | `migrate-records` |
| Persistent runtime checkpoints | Complete | `runtime-checkpoint` |
| Automatic resume and record-based recovery | Complete | `runtime-status`, `runtime-resume` |
| Structured human approval for L3 | Complete | `approve`, `approval.schema.json` |
| Deterministic verification reports | Complete | `doctor`, `verify` |
| Process metrics and host metrics ingestion | Complete | `metrics` |
| Persistent version registry | Complete | `registry-update`, `registry-list` |
| Automatic improvement candidates | Complete | `improvements` |
| Codex and Claude Code adapters | Complete | `.codex/`, `.claude/`, `adapters/` |
| Windows, Ubuntu, and Rocky Linux 8 CI | Complete | `.github/workflows/tests.yml` |

## Canonical records

The v3 schema family contains:

- Work Item
- Artifact
- Finding
- Verification
- Decision
- Iteration
- Human Approval

`migrate-records` defaults to dry-run and requires explicit Verification role
mapping. `--write` validates a complete staged copy, retains the original as a
sibling backup, and swaps directories only after validation.

## Runtime and control plane

- `runtime-checkpoint` stores a digest-bound checkpoint outside the records
  directory.
- `runtime-status --records` compares canonical records with stored state.
- `runtime-resume --records` selects a matching checkpoint, skips corrupt
  checkpoints, and rebuilds state from records when storage is missing or
  stale.
- `approve` writes a human approval only when the exact
  `APPROVE <artifact>@<version>` confirmation is supplied.
- L3 ACCEPT requires final-version Reviewer and Challenger PASS evidence plus a
  referenced human approval record.

## Stage 3

- `metrics` reports workflow metrics and accepts optional host metrics for
  turns, tool calls, tokens, elapsed time, and cost.
- `registry-update` and `registry-list` persist Work Item and Artifact version
  evidence by canonical record digest in per-run files, so concurrent updates
  do not overwrite one another.
- `improvements` generates deterministic candidates from recurring findings,
  failed or blocked checks, repeated repairs, and unresolved medium risks.

Candidate generation does not modify artifacts or promote rules automatically.

## Boundaries, not unfinished work

- The kit does not launch models or sub-agents; Codex, Claude Code, or another
  orchestrator supplies the execution host.
- Human approval records operator intent but do not cryptographically
  authenticate the person. Regulated deployments must add host identity and
  access controls.
- The default GLM provider remains an external availability constraint; the
  validated Claude path is `qwen3.7-plus`.
- Literal CentOS 8 is not booted; Rocky Linux 8 is the executed compatibility
  target.
