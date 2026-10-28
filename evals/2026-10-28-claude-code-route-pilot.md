# Claude Code Route Pilot - 2026-10-28

## Purpose

Check whether the v0.3 route contract is followed by Claude Code more reliably
than the v0.2 Skill, under the same model and budget. This is a protocol
conformance pilot, not a full coding-task benchmark.

## Environment

| Item | Value |
|---|---|
| Claude Code | 2.1.267 |
| Model | `deepseek/deepseek-flash` through the local CCR endpoint |
| Baseline | commit `9057930` (v0.2.0) |
| Candidate | commit `0101b9c` (v0.3.0) |
| Mode | `--bare`, `--permission-mode plan`, `--no-session-persistence` |
| Tools | `Read,Glob,Grep` |
| Budget | `$0.20` per run |
| Repetitions | 3 per variant |

The same prompt was used for both variants. It asked Claude Code to read the
specified Skill and classify three scenarios:

1. One README typo.
2. A two-file pagination fix with tests.
3. An irreversible database migration plus production configuration change.

The required output had five fields: `tier`, `roles`,
`review_independence`, `max_repair_iterations`, and
`human_approval_required`.

## Results

| Variant | Success | Turns | Mean cost | Mean duration |
|---|---:|---:|---:|---:|
| v0.2.0 | 0/3 | 29, 39, 46 | $0.2088 | 29.0 s |
| v0.3.0 | 3/3 | 4, 4, 4 | $0.0541 | 5.2 s |

Raw cost observations:

- v0.2.0: `$0.200526`, `$0.203263`, `$0.222509`
- v0.3.0: `$0.053007`, `$0.052583`, `$0.056758`

All v0.3 runs returned the expected L0/L2/L3 contracts. All v0.2 runs exhausted
the per-run budget before returning a final classification. The provider
overshot the configured ceiling on some failed runs because the final API call
could not be interrupted mid-request.

## Interpretation

This pilot supports one narrow claim: under the tested model, tools, and
budget, the explicit v0.3 route removed an unstable classification loop.

It does not establish:

- better correctness on real repository edits;
- lower cost after code changes and tests;
- Reviewer or Challenger effectiveness in live subagents;
- cross-model or cross-host generalization;
- article-level performance claims.

The local CCR setup still prints an `unrecognized_model` warning for the
configured aliases, although all runs above completed through the reported
`deepseek/deepseek-flash` model. Treat model routing as a separate operational
issue.

