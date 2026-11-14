# Stage 2 Hardening - 2026-11-14

## Work Item

- ID: `WI-LE-STAGE2-20261114`
- Pack: `software-development`
- Risk: `medium`
- Control route: `L2`, full in-session records
- Repair budget: `3`
- Cumulative baseline: `c02f1f6`

## Acceptance Criteria

- `AC-ANCESTRY`: `check-records` resolves stable IDs, criteria, versions,
  Finding recurrence, Decision evidence, and Artifact/Iteration ancestry.
- `AC-COMPAT`: the Bash installer and full suite pass in Rocky Linux 8 with
  Python 3.8.
- `AC-MODEL`: Claude Code documentation names `qwen3.7-plus` as the validated
  local path and records the GLM 403 as a provider limitation.
- `AC-ACTIONS`: CI uses `checkout@v5` and `setup-python@v6` without Node 20
  deprecation warnings.
- `AC-REGRESSION`: all tests, verification, source doctor, both installed
  doctors, compilation, and diff hygiene pass.

## Implemented Changes

- Added `check-records --dir` with bundled-schema validation, cross-record
  reference resolution, Decision evidence checks, Finding recurrence rejection,
  and explicit Iteration `output_versions`.
- ACCEPT must target the final lineage version; open questions, non-independent
  L2 review, and controller-only L3 approval are rejected.
- Replaced the Bash installer's `find` dependency with Bash globstar recursion,
  allowing the Rocky Linux 8 minimal image to execute the installer test.
- Added Rocky Linux 8 + Python 3.8 to CI.
- Documented `qwen3.7-plus` as the verified Claude Code model path and kept the
  upstream GLM 403 as a limitation.
- Upgraded GitHub Actions to `checkout@v5` and `setup-python@v6`.

## Verification

- Local suite: `53/53 OK`
- Configured verify: PASS with project repair budget `3` and latest report
  `loop-engineering-stage2-v3b-20261114-192204`.
- Source and Codex/Claude installed doctors: PASS
- GitHub Actions baseline `43587870598`: five jobs PASS at `136f42a`.
- The final repair commit is awaiting its own pushed matrix; it is not counted
  as PASS until that follow-up run succeeds.
- The same remote run uses the upgraded Actions and emits no Node 20
  deprecation warning.
- Rocky Linux 8 installs Python 3.8.17 and runs the same full suite.

## Residual Risks

- Literal CentOS 8 was not booted; Rocky Linux 8 is the executed compatible
  target.
- The default GLM provider remains blocked by an upstream 403; use the verified
  `qwen3.7-plus` path until it recovers.
- Durable Stage 2 storage, automatic recovery, and human-approval runtime are
  still deferred. The delivered Stage 2 increment is deterministic record
  resolution.
