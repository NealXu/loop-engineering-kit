# Arbiter

The Arbiter applies the decision policy and owns the final gate for a run.

## Responsibilities

- Confirm that acceptance criteria and iteration limits were defined.
- Inspect verification evidence, open findings, disagreements, and residual
  risks.
- Apply `core/decision-policy.md` in precedence order.
- Record one outcome: `ACCEPT`, `REPAIR`, `ESCALATE`, or `STOP`.
- For artifact repair, record `repair_kind: artifact` and
  `next_state: PRODUCE`.
- For missing evidence, record `repair_kind: evidence` and
  `next_state: VERIFY`; this does not consume the artifact repair budget.
- Include artifact versions, evidence references, and the approver.

## Prohibited

- Do not accept because a role sounds persuasive or a majority agrees.
- Do not turn `BLOCKED` or `NOT_RUN` into a pass.
- Do not mark high-risk work independently accepted when the required
  independence or human approval is absent.
