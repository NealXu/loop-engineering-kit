# Claude Code Harness Pilot - 2026-10-28

## Purpose

Check whether the v0.3 route contract improved protocol conformance and real
code-task outcomes over the v0.2 Skill under the same model and budget.

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

## Coding-task follow-up

A second pilot used two dependency-free repositories:

1. Single-file `slugify` repair.
2. Two-file quantity and order-discount repair.

Each run was graded by the public test and hidden tests injected only after the
agent stopped. Tests were not modifiable by the evaluation prompt. The first
three valid runs per variant used `$0.50` each and no `Task` tool.

| Task | Variant | Hidden success | Mean turns | Mean cost |
|---|---|---:|---:|---:|
| slugify | v0.2.0 | 3/3 | 14.0 | $0.3298 |
| slugify | v0.3.0 | 3/3 | 24.7 | $0.3481 |
| orders | v0.2.0 | 3/3 | 25.7 | $0.3595 |
| orders | v0.3.0 | 2/3 | 26.3 | $0.5525 |

All runs passed the visible tests. The v0.3 orders failure was a rounding
semantic bug: it discounted each line instead of rounding once on the order
subtotal. This is exactly the type of issue an independent reviewer should
catch; however, bare Claude Code did not expose the custom subagent reliably.
A normal-mode smoke test spawned `reviewer` successfully, but the full plugin
context exhausted its budget before returning a review.

## v0.3.1 lean follow-up

The first follow-up showed the route records were too verbose. v0.3.1 added:

- no formal records for L0;
- a compact brief for L1;
- an in-session full loop for L2;
- persisted machine records only for L3 or explicit project opt-in.

Follow-up observations:

- L1 slugify: 2/2 hidden passes, 14.5 mean turns, $0.2310 mean cost.
- L2 orders: 2/4 hidden passes, 27.3 mean turns, $0.3694 mean cost.
- The new version stopped writing unrequested `artifacts/` files.
- The remaining L2 failures had the same per-line discount rounding mistake.
- Adding a rule for boundary/aggregate checks did not resolve an ambiguous
  rounding contract; an independent reviewer or user clarification is still
  required when the visible tests do not define the intended semantics.

The sample is too small and model-specific for a general performance claim. It
does support keeping the lean L0/L1 path and marks independent live review as
unfinished evidence, not as a success.

The local CCR setup still prints an `unrecognized_model` warning for the
configured aliases, although all reported runs completed through the reported
`deepseek/deepseek-flash` model. Treat model routing as a separate operational
issue.

