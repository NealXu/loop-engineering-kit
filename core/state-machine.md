# Loop State Machine v1

## States

| State | Entry condition | Exit |
|---|---|---|
| `DEFINE` | A work request exists | `PRODUCE` once goal, constraints, IDed acceptance criteria, risk level, and iteration budget are explicit |
| `PRODUCE` | Scope is defined | verification/review/challenge once at least one artifact version exists |
| `VERIFY` | An artifact version exists | `RECONCILE` after required checks return evidence |
| `REVIEW` | An artifact version exists | `RECONCILE` after findings are recorded |
| `CHALLENGE` | Goal and artifact exist | `RECONCILE` after assumptions, alternatives, and failure paths are recorded |
| `RECONCILE` | Required role outputs exist | `DECIDE` after deduplication and factual confirmation |
| `DECIDE` | Evidence and open findings are known | `ACCEPT`, `REPAIR`, `ESCALATE`, or `STOP` |
| `REPAIR` | Decision is `REPAIR`; artifact changes require budget, evidence-only work does not | the decision's declared `next_state` |
| `ACCEPT` | Gate passes | terminal |
| `ESCALATE` | A human or higher authority must decide | terminal for the current run |
| `STOP` | Budget, authority, or dependency prevents progress | terminal |

`VERIFY`, `REVIEW`, and `CHALLENGE` may run in parallel. `RECONCILE` starts
only after every stage required by the selected pack has returned.
The control route determines which stages are required. L0 may use the host's
direct edit-and-check path; L1 requires verification but not independent
review; L2 requires independent review; L3 also requires challenge and human
approval before irreversible actions.

## Transition Guards

- Missing acceptance criteria blocks `DEFINE -> PRODUCE`.
- A material open question that can change goal, acceptance semantics, scope,
  data handling, or irreversible effects blocks `DEFINE -> PRODUCE`. Resolve it
  with the user or an authoritative source, or record an explicit assumption
  and rollback; review cannot replace that decision.
- A route that permits no artifact repair blocks a second artifact version
  unless the Controller explicitly redefines the task.
- Missing artifact version blocks review and verification.
- Missing evidence is not a pass.
- A required check failure or open `blocking`/`high` finding permits only
  `REPAIR`, `ESCALATE`, or `STOP`.
- Missing required evidence produces `REPAIR` with `repair_kind: evidence` and
  `next_state: VERIFY`; this does not consume the artifact repair budget.
- Artifact repair requires `repair_kind: artifact`, remaining budget, and
  `next_state: PRODUCE`.
- An unresolved material disagreement prevents `ACCEPT` until the Arbiter
  records a rule-based resolution or escalates it.
- Reaching the artifact repair limit permits only `STOP`, `ESCALATE`, or an
  evidence-only verification route that does not change the artifact.
- A repeated failure fingerprint with no artifact change permits only `STOP`
  or `ESCALATE` unless new evidence changes the diagnosis.
- No configured checks prevents automatic `ACCEPT`.

## Parallelism

Review and challenge should receive the same immutable artifact version. Their
outputs are independent records, not a shared conversation. Reconciliation may
merge duplicate findings, but must preserve source, evidence, and any
disagreement.

## Recovery

The state and version identifiers are part of the records so a later run can
resume from the last completed stage. Persistent runtime storage is a Stage 2
capability; until implemented, the Controller records the same identifiers in
the run report.

Context compression is not recovery by itself. A resumed run needs the frozen
artifact version, original evidence references, open findings, and the exact
next state. When host metrics exist, retain turn count, tool-call count, token
use, and cost alongside the outcome.
