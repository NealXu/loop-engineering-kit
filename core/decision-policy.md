# Decision Policy v1

## Severity

| Severity | Meaning | Gate effect |
|---|---|---|
| `blocking` | Violates a required criterion, safety rule, or makes delivery unusable | Must repair or stop |
| `high` | Likely incorrect or unsafe under relevant conditions | Must repair before acceptance |
| `medium` | Real limitation with a bounded workaround | May accept only with recorded residual risk |
| `low` | Improvement with no material delivery impact | May remain open |

## Verification Status

`PASS` requires executed evidence. `FAIL` requires a failed check or proven
counterexample. `BLOCKED` means an environmental dependency prevents a check.
`NOT_RUN` means the check was intentionally or accidentally skipped. Neither
`BLOCKED` nor `NOT_RUN` may be treated as a pass.

## Decision Precedence

Apply the first matching rule:

1. A timeout, missing external dependency, or required artifact change after
   the repair budget is exhausted prevents progress: `STOP`, or `ESCALATE`
   when a human can authorize a changed scope or accept the remaining risk.
2. A required check fails, or a `blocking`/`high` finding is open: `REPAIR`.
3. Required evidence is missing or a material disagreement can be resolved by
   a bounded experiment: `REPAIR` with `repair_kind: evidence` and
   `next_state: VERIFY`.
4. An unresolved disagreement requires authority or risk acceptance: `ESCALATE`.
5. All required criteria have passing evidence, no `blocking`/`high` finding is
   open, and the changes are understood: `ACCEPT`.

Before `ACCEPT`, run `python loop_engineering/cli.py check-finding --input
<finding.json> --work-item <work-item.json> --artifact <artifact.json>
--verifications-dir <directory>` for every closed `high`, `blocking`, or
recurring Finding, or apply the equivalent host validation. Every regression
Verification must exist, be `PASS`, match the Artifact id/version, and contain
executed evidence and the Finding id. The directory may use any JSON filename;
records are selected by `kind: verification`. A missing or invalid prevention
contract blocks acceptance.
`check-finding` validates the Finding and its regression evidence, not the
overall Decision: an open `high` or `blocking` Finding is valid for REPAIR or
STOP and blocks only ACCEPT.

A failure fingerprint combines the failed check, failure signature, and
artifact versions. If the same fingerprint repeats with no artifact change,
the loop has not made progress: `STOP`, or `ESCALATE` when new authority or a
changed scope can unlock it.

## Acceptance Record

An `ACCEPT` decision records:

- artifact versions covered by the decision;
- criterion ID to verification ID mapping;
- optional failed or skipped checks and why they do not affect acceptance;
- accepted residual risks and their owner;
- unresolved low/medium findings;
- whether review independence was available;
- approver identity or `controller` when no human approval is required.

## Repair Budget

The default maximum is three repair iterations. Each iteration records the
findings it targets, changed artifact versions, and rerun checks. Repeating the
same failure without new evidence stops the loop rather than consuming the
budget silently. Only `repair_kind: artifact` consumes the budget; an
evidence-only `repair_kind: evidence` cycle does not.

The selected control tier may use a smaller budget. L0 uses zero, L1 uses two,
and L2/L3 default to three. A budget is a ceiling, not a target.
