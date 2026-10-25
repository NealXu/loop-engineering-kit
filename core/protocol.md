# Universal Work Loop Protocol v1

This protocol defines a host-neutral work loop. Codex, Claude Code, and other
agent environments execute the loop; they are not the loop itself.

## Concepts

- A **role** defines responsibilities, allowed inputs and outputs, and
  prohibited actions.
- A **workflow** defines role order, parallel work, repair paths, and stopping
  points.
- A **workflow pack** binds the generic roles and artifacts to one domain.
- In the target runtime, the **engine** applies the state machine and decision
  policy so progress does not depend on model memory. Until that runtime exists,
  the Controller records the same state and version identifiers manually.
- The **host adapter** maps roles to agents, skills, permissions, and commands.

## Lifecycle

`DEFINE -> PRODUCE -> VERIFY + REVIEW + CHALLENGE -> RECONCILE -> DECIDE`

`DECIDE` ends in exactly one of `ACCEPT`, `REPAIR`, `ESCALATE`, or `STOP`.
Artifact repair returns to `PRODUCE`; evidence-only repair returns to `VERIFY`.
Other repair routes follow the decision's declared `next_state`.

## Required Records

Every non-trivial run should produce these machine-readable records when they
apply:

| Record | Purpose |
|---|---|
| Work Item | id, selected pack_id, goal, constraints, priority, acceptance criteria |
| Artifact | id, work_item_id, version, type, content, source |
| Finding | actionable defect, risk, or challenge |
| Verification | artifact id/version, check method, result, and evidence |
| Decision | work_item_id, artifact_versions, outcome, evidence, disagreement, approver |
| Iteration | work_item_id, cycle, input versions, changes, and result |

The canonical field contract is in `core/artifact-schema/`. Human-readable
reports may summarize records, but must not replace their evidence.

## Adversarial Rules

- Independence: review and challenge start from the goal and deliverable, not
  from the producer's explanation.
- Falsifiability: each finding names evidence, a counterexample, or a concrete
  verification method.
- Structure: each finding includes severity, evidence, impact, and required
  action.
- Disagreement: consensus is not required. Resolve it with evidence, a rule, a
  bounded experiment, or escalation.
- Recovery: repair addresses named findings and reruns affected checks.
- Stopping: acceptance criteria, iteration budget, timeout, and escalation path
  are defined before work starts.

## Authority Boundary

The Producer creates and repairs. The Verifier records evidence. The Reviewer
and Challenger find different classes of problems. The Arbiter applies the
decision policy and must not accept based only on role persuasion.

One model may perform multiple duties in low-risk work. High-risk work should
use an independent session, a different model, or human approval. A combined
role must be disclosed and cannot be described as independent.

## Pack Contract

A workflow pack defines:

1. role bindings and required independence;
2. domain artifacts and acceptance criteria;
3. deterministic checks and evidence requirements;
4. review and challenge focus areas;
5. escalation conditions and residual-risk rules.

The first implemented packs are `packs/software-development/` and
`packs/architecture-design/`.
