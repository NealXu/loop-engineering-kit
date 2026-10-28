---
name: loop-engineering
description: Evidence-driven multi-role work loop with production, deterministic verification, independent review/challenge, repair, and explicit acceptance. Includes software-development and architecture-design packs; extendable to other domains.
---

# Loop Engineering
The parent session is the Controller. Use the smallest loop that fits the
task; do not start every role for every request.

Locate the kit root before starting. In this repository it is the ancestor
containing `core/` and `loop_engineering/cli.py`; in an installed package those
paths are emitted beside this `SKILL.md`.

1. **Route:** classify the work as L0-L3 from expected file count, risk,
   ambiguity, and irreversibility. From the kit root, use
   `python loop_engineering/cli.py route --risk <level> --files <count>`
   with `--trivial`, `--ambiguous`, or `--irreversible` when applicable.
   The route selects roles, independence, repair budget, and stop conditions.
   L0 is a trivial direct change; L1 adds Verifier; L2 adds independent
   Reviewer; L3 also adds Challenger and human approval before irreversible
   actions.
2. **Define:** read project instructions and `core/protocol.md`; select a pack;
   create a Work Item with `id` and `pack_id`; state goal, constraints, risk,
   acceptance criteria, and repair budget.
   At the end of Define, write a short run brief with the goal, acceptance
   criteria, current artifact references, open questions, and next action.
3. **Produce:** use `roles/producer.md`; create the smallest complete, versioned
   Artifact linked by `work_item_id`, with a stable `id` and `version`, and
   capture assumptions.
4. **Verify:** use `roles/verifier.md`; run native checks. If the Python
   CLI/config exists, run `python loop_engineering/cli.py verify --root
   <project-root>` from the kit root (`python3` on Linux, `py -3` on Windows).
   Link each Verification to the tested Artifact id/version.
5. **Review and challenge:** use only the roles selected by the route. For L2+,
   give the independent Reviewer the frozen artifact, acceptance criteria, and
   evidence, without the Producer's rationale. Start Challenger for L3 or when
   a material assumption remains unresolved. If the host cannot provide an
   independent session, perform the duty in-session and disclose that it was
   not independent.
6. **Reconcile:** deduplicate findings, confirm facts, preserve material
   disagreement, and distinguish root cause from symptom.
7. **Decide:** use `roles/arbiter.md` and `core/decision-policy.md`; record
   `ACCEPT`, `REPAIR`, `ESCALATE`, or `STOP`. A `REPAIR` decision also records
   both fields: artifact repair uses `repair_kind: artifact` and
   `next_state: PRODUCE`; missing evidence uses `repair_kind: evidence` and
   `next_state: VERIFY`. Include `work_item_id` and `artifact_versions`.
8. **Repair:** if required, use the pack workflow and send named findings to the
   Producer. Create an Iteration with the same `work_item_id`, input versions,
   and changes. Create a new Artifact version or perform evidence-only checks
   and rerun affected checks. Stop at the iteration limit.
   Before repairing, update the run brief with the failing check, changed
   artifact versions, evidence, open findings, and next action. Do not delete
   the original evidence.
9. **Finish:** report artifact versions, exact commands and outcomes, findings,
   residual risks, checks not run, and when available, turns, tool calls, token
   use, and cost. A repeated failure fingerprint with no artifact change stops
   further repair unless new evidence changes the diagnosis.

Use the record shapes in `core/artifact-schema/`. Never fabricate results or
treat BLOCKED/NOT_RUN as PASS. Ask before destructive, irreversible,
production-impacting, or credential-related actions.
