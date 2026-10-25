---
name: loop-engineering
description: Evidence-driven multi-role work loop with production, deterministic verification, independent review/challenge, repair, and explicit acceptance. Includes software-development and architecture-design packs; extendable to other domains.
---

# Loop Engineering
The parent session is the Controller. Default maximum: 3 repair iterations.

Locate the kit root before starting. In this repository it is the ancestor
containing `core/`; in an installed package the `core/`, `roles/`, `workflows/`,
and `packs/` directories are emitted beside this `SKILL.md`.

1. **Define:** read project instructions and `core/protocol.md`; select a pack;
   create a Work Item with `id` and `pack_id`; state goal, constraints, risk,
   acceptance criteria, and repair budget.
2. **Produce:** use `roles/producer.md`; create the smallest complete, versioned
   Artifact linked by `work_item_id`, with a stable `id` and `version`, and
   capture assumptions.
3. **Verify:** use `roles/verifier.md`; run native checks. If the Python
   CLI/config exists, run `python loop_engineering/cli.py verify --root .`
   (`python3` on Linux, `py -3` on Windows). Link each Verification to the
   tested Artifact id/version.
4. **Review and challenge:** use `roles/reviewer.md` and
   `roles/challenger.md`. Use independent subagents when supported. If not,
   perform the duties in-session and disclose that they were not independent.
5. **Reconcile:** deduplicate findings, confirm facts, preserve material
   disagreement, and distinguish root cause from symptom.
6. **Decide:** use `roles/arbiter.md` and `core/decision-policy.md`; record
   `ACCEPT`, `REPAIR`, `ESCALATE`, or `STOP`. A `REPAIR` decision also records
   both fields: artifact repair uses `repair_kind: artifact` and
   `next_state: PRODUCE`; missing evidence uses `repair_kind: evidence` and
   `next_state: VERIFY`. Include `work_item_id` and `artifact_versions`.
7. **Repair:** if required, use the pack workflow and send named findings to the
   Producer. Create an Iteration with the same `work_item_id`, input versions,
   and changes. Create a new Artifact version or perform evidence-only checks
   and rerun affected checks. Stop at the iteration limit.
8. **Finish:** report artifact versions, exact commands and outcomes, findings,
   residual risks, and checks not run.

Use the record shapes in `core/artifact-schema/`. Never fabricate results or
treat BLOCKED/NOT_RUN as PASS. Ask before destructive, irreversible,
production-impacting, or credential-related actions.
