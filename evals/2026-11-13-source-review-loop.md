# Source-Derived Loop Improvements - 2026-11-13

## Purpose

Record the Work Item, acceptance criteria, verification mapping, and limitations
for the review-driven changes informed by two public posts.

## Source Provenance

- https://x.com/leo_xiaolei/status/2120832443041357961/video/1
- https://x.com/kylewmi/status/2117471459803328912

The first source is a Chinese translation of Lauren Tan's talk. The second is a
third-party synthesis that includes automated transcription. Their reported
delivery metrics are attributed observations, not benchmark evidence for this
project.

## Work Item

- ID: `WI-LE-SOURCES-20261113`
- Pack: `software-development`
- Risk: `medium`
- Repair budget: `50` is a controller-managed safety ceiling for the user's
  instruction to continue through the final independent gate, not a numeric
  value requested by the user. The tracked project default remains `3`.
- Session records: `$env:TEMP\loop-engineering-session-WI-LE-SOURCES-20261113`

Acceptance criteria:

- `AC-CONTRACT`: role-record persistence, verification evidence, host
  instructions, and the semantic ambiguity gate are consistent.
- `AC-GUARD`: repeated, high, and blocking findings have executable prevention
  checks with regression evidence and a recorded fallback when structure is not
  used.
- `AC-VERIFY-SKILL`: the verification-skill template is present, doctor-checked,
  and included by both installers.
- `AC-CRITERIA-ID`: schemas v2 link stable criterion IDs through Work Item,
  Verification, and Decision records.
- `AC-REGRESSION`: tests, doctor, configured verification, compilation, and diff
  checks pass.

## Verification Summary

- Full suite: `python -m unittest discover -s tests -v`
- Configured checks: `python loop_engineering/cli.py verify --root . --report-dir <dir>`
- Finding gate: `python loop_engineering/cli.py check-finding --input <finding> --work-item <work-item> --artifact <artifact> --verifications-dir <dir>`
- Environment: `python loop_engineering/cli.py doctor`
- Compilation: `python -m compileall -q loop_engineering tests`
- Diff hygiene: `git diff --check`

Canonical records are session-only working files under the ignored review
directory and are excluded from the delivered artifact. The tracked delivery evidence is
`evals/2026-11-13-source-review-evidence.json`; it contains the criterion map,
artifact version, file list, findings, verification IDs, budget, and iteration
count. Regression Verification records bind to Findings through `finding_id`;
`check-finding` scans JSON records by kind.

## Authorization

On 2026-11-13 the user explicitly directed:

> 继续直到最终独立门禁通过，到达“全部完成”

This authorizes continuing repairs until the final independent gate passes; it
does not specify a numeric budget. The controller records `50` as a nonbinding
safety ceiling in the current-run config. The directive did not authorize
deployment, publication, or credential-related actions.

## Repair History

Artifact versions 2 through 27 each have a session Iteration record under
`$env:TEMP\loop-engineering-session-WI-LE-SOURCES-20261113\iterations`.
Each record identifies the input version, targeted findings, changes, and
continue result. The final gate covers version 27.

## Actual Findings

The review defects that drove the prevention work are recorded for this session as:

- `finding-F-CONTRACT.json` with `V-FINDING-CONTRACT`
- `finding-F-GUARD.json` with `V-FINDING-GUARD`
- `finding-F-OUTPUT.json` with `V-FINDING-OUTPUT`

Each regression Verification is `PASS`, targets `A-LE-SOURCES` version 27,
contains a matching `finding_id`, and covers the relevant criterion. The
Arbiter path is:

```text
SESSION_RECORDS=%TEMP%\loop-engineering-session-WI-LE-SOURCES-20261113
python loop_engineering/cli.py check-finding --input <finding> \
  --work-item %SESSION_RECORDS%\work-item.json \
  --artifact %SESSION_RECORDS%\artifact.json \
  --verifications-dir %SESSION_RECORDS%
```

## Post-Delivery Verification

- External JSON Schema engine: PowerShell `Test-Json` accepted six valid records
  and rejected six invalid cases.
- Codex subagent: 48 tests, `doctor`, and the three actual Finding gates passed.
- Claude Code `2.1.267`: both project and User Scope verifier sessions returned
  `CLAUDE_VERIFY_PASS`; the validated model was `qwen3.7-plus`.
- The default CCR `opencode/glm-5.3-flash` route remained blocked by an upstream
  403, so it is recorded as an environment limitation rather than a pass.
- Real User Scope installation succeeded for both hosts with timestamped
  backups. The installed `doctor --mode installed` exits `0` for Codex and
  Claude copies.
- CI targets Python 3.8 and 3.12 on Ubuntu and Windows. CentOS 8 is not covered
  by CI, and these non-Windows targets were not executed locally.

## Limitations

- Python 3.8, Ubuntu/CentOS 8, and the remote CI workflow have not executed.
- The default GLM provider remains blocked; the validated Claude path uses
  `qwen3.7-plus`.
- Stage 2 cross-record ancestry and reference resolution remain deferred.
