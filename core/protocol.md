# Universal Work Loop Protocol v1

This protocol defines a host-neutral work loop. Codex, Claude Code, and other
agent environments execute the loop; they are not the loop itself.

## Concepts

- A **role** defines responsibilities, allowed inputs and outputs, and
  prohibited actions.
- A **workflow** defines role order, parallel work, repair paths, and stopping
  points.
- A **workflow pack** binds the generic roles and artifacts to one domain.
- The **runtime** persists the same state and version identifiers so progress
  does not depend on model memory. `runtime-checkpoint`, `runtime-status`, and
  `runtime-resume` implement checkpointing and automatic record-based recovery.
- The **host adapter** maps roles to agents, skills, permissions, and commands.

## Lifecycle

`DEFINE -> PRODUCE -> VERIFY + REVIEW + CHALLENGE -> RECONCILE -> DECIDE`

`DECIDE` ends in exactly one of `ACCEPT`, `REPAIR`, `ESCALATE`, or `STOP`.
Artifact repair returns to `PRODUCE`; evidence-only repair returns to `VERIFY`.
Other repair routes follow the decision's declared `next_state`.

## Control Route

Select the smallest complete loop before producing an artifact:

| Tier | Use when | Required roles | Review independence | Repair budget | Records |
|---|---|---|---|---:|---|
| `L0` | Low-risk trivial change with no ambiguity | none or the direct host workflow | not required | 0 | none |
| `L1` | Bounded single-file work | Producer, Verifier, Arbiter | not required | 2 | compact |
| `L2` | Multiple files, medium risk, or ambiguity | Producer, Verifier, Reviewer, Arbiter | required | 3 | full |
| `L3` | High/critical risk or an irreversible action | all five roles | required | 3 | audited |

Ambiguity promotes the route. Irreversibility always requires `L3` and human
approval before the irreversible action. A host may combine duties only when
the route allows it and must disclose `non_independent` review.

The route is a control budget, not evidence. The Controller records the chosen
tier and later reports omitted roles or checks.

`route --max-repairs <n>` may record an explicit user-authorized override for
the current run. The Work Item's `max_repair_iterations` is authoritative, and
the current-run verification config must surface the same value until the run
ends. The tracked project default remains unchanged.

`compact` states the goal, acceptance criteria, and budget in the working
conversation; it does not create machine-readable records. `full` performs the
complete role loop and keeps canonical role records in-session unless the
project explicitly requests persistence. `audited` persists the record shapes
in `core/artifact-schema/`.

## Working Set

At Define, after the first artifact version, and before an artifact repair,
update a short run brief containing:

- current goal and acceptance criteria;
- artifact ids and versions;
- verification evidence references;
- open findings and disagreements;
- the next action and the current failure fingerprint.

Before `PRODUCE`, resolve any open question that can change goal, acceptance
semantics, scope, data handling, or irreversible effects. If no user or
authoritative source is available, record an explicit assumption and rollback.
Do not use independent review as a substitute for a product-semantics decision.

The brief is a working set, not a replacement for source evidence. Do not
delete original command output or trajectory records merely to shorten the
conversation. Preserve the information needed to resume and audit the run.

## Required Records

Every non-trivial run should produce these machine-readable records when they
apply:

| Record | Purpose |
|---|---|
| Work Item | id, selected pack_id, goal, constraints, priority, risk, repair budget, acceptance criteria with stable IDs |
| Artifact | id, work_item_id, version, content, source, canonical content_hash |
| Finding | actionable defect, risk, or challenge |
| Verification | artifact id/version, criterion_ids, check method, result, and evidence |
| Decision | work_item_id, artifact_versions, criterion-to-verification mapping, outcome, evidence, disagreement, approver |
| Iteration | work_item_id, cycle, input versions, changes, and result |
| Human Approval | exact final Artifact version, named human approver, statement, timestamp, and confirmation token |

The canonical field contract is in `core/artifact-schema/`. Human-readable
reports may summarize records, but must not replace their evidence.
Verification and approval records bind to the Artifact `content_hash`; a
Decision maps every covered version to its hash. This prevents an in-place
replacement of the same `id@version` from satisfying existing gates.

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
- No progress: if the same check fails with the same failure fingerprint and
  no artifact version changes, stop or escalate instead of spending the
  remaining budget on another identical turn.

## Authority Boundary

The Producer creates and repairs. The Verifier records evidence. The Reviewer
and Challenger find different classes of problems. The Arbiter applies the
decision policy and must not accept based only on role persuasion.

One model may perform multiple duties in low-risk work. High-risk work should
use an independent session, a different model, or human approval. A combined
role must be disclosed and cannot be described as independent.

## Runtime And Approval

Persistent checkpoints are stored outside the canonical records directory and
bound to a digest of the record set. A stale or missing checkpoint is rebuilt
from canonical records; corrupt checkpoints are skipped.

L3 work uses the `approve` command after Reviewer and Challenger PASS evidence
exists. The command requires the exact `APPROVE <artifact>@<version>`
confirmation and writes a canonical Human Approval record. L3 ACCEPT must
reference that record for the final Artifact version.

## Pack Contract

A workflow pack defines:

1. role bindings and required independence;
2. domain artifacts and acceptance criteria with stable IDs;
3. deterministic checks and evidence requirements;
4. review and challenge focus areas;
5. escalation conditions and residual-risk rules.

The first implemented packs are `packs/software-development/` and
`packs/architecture-design/`.
