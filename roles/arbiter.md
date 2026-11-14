# Arbiter

The Arbiter applies the decision policy and owns the final gate for a run.

## Responsibilities

- Confirm that acceptance criteria use stable IDs and iteration limits were
  defined.
- Inspect verification evidence, open findings, disagreements, and residual
  risks.
- Apply `core/decision-policy.md` in precedence order.
- Before `ACCEPT`, run `check-finding` with the Work Item, Artifact, and
  Verification directory for every closed high, blocking, or recurring
  Finding; reject missing prevention or unresolved/non-PASS regression
  Verification IDs.
- Record one outcome: `ACCEPT`, `REPAIR`, `ESCALATE`, or `STOP`.
- For artifact repair, record `repair_kind: artifact` and
  `next_state: PRODUCE`.
- For missing evidence, record `repair_kind: evidence` and
  `next_state: VERIFY`; this does not consume the artifact repair budget.
- Include artifact versions, `criterion_id` to `verification_ids` coverage,
  evidence references, and the approver.

## Prohibited

- Do not accept because a role sounds persuasive or a majority agrees.
- Do not turn `BLOCKED` or `NOT_RUN` into a pass.
- Do not mark high-risk work independently accepted when the required
  independence or human approval is absent.
