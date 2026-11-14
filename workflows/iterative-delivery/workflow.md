# Iterative Delivery Workflow

Use this workflow for a bounded task that must produce a reviewable result.

1. **Route:** select L0-L3 from expected files, risk, ambiguity, and
   irreversibility. The route determines required roles and the repair budget.
   A trivial L0 change uses the host's direct edit-and-check path. L1 uses a
   compact three-line brief. For a compact L1 route, use only this path: state
   the three-line brief, produce, run every check required by the selected pack
   and acceptance criteria (or one relevant check when none are configured),
   and decide in-session. Do not create a Work Item or Artifact record. A
   persistence request does not override compact; re-route the task as full or
   audited before persistence. L2
   keeps the full loop. Keep canonical role records in-session unless the
   project explicitly requests persistence. Only L3 or that explicit request
   writes them.
2. **Define (`full`/`audited`):** create the Work Item with a stable `id` and
   `pack_id`, assign
   roles, and state `max_repair_iterations` and risk level. Give every
   acceptance criterion a stable ID in the `acceptance_criteria` map and use it
   as the key; the map value is the statement.
   Update the run brief with the goal, acceptance criteria, open questions, and
   next action.
   A material open question that can change goal, acceptance semantics, scope,
   data handling, or irreversible effects blocks `PRODUCE` until the user or an
   authoritative source resolves it, or an explicit assumption and rollback are
   recorded. A Reviewer cannot decide product semantics.
3. **Produce:** create an Artifact with the same `work_item_id`, a stable `id`,
   and an explicit `version`; record assumptions.
4. **Verify:** execute the pack's required checks and record each Verification
   against that Artifact `id` and `version`, including the covered
   `criterion_ids`. When the CLI is used, pass an explicit `--report-dir`: use a
   session-temporary path for L1/L2 unless persistent evidence is requested,
   and a project path for L3. For repeatable GUI, browser, API, or multi-step
   flows, use
   `packs/software-development/verification-skill.md`.
5. **Review and challenge:** run only the roles required by the route. For L2+,
   the Reviewer receives the frozen artifact and evidence without the
   Producer's rationale. L3 also uses the Challenger. They may run in parallel
   against the same artifact version.
6. **Reconcile:** deduplicate findings, verify facts, preserve disagreements,
   and separate symptoms from root causes.
7. **Decide:** the Arbiter applies the decision policy and records the
   `work_item_id`, covered `artifact_versions`, evidence, and approver. An
   `ACCEPT` uses a map keyed by `criterion_id` to passing `verification_ids`; a
   `REPAIR` records open findings and failing or missing evidence instead.
   Before `ACCEPT`, run `check-finding` for each resolved high, blocking, or
   recurring Finding.
8. **Repair:** update the run brief with the failure fingerprint, then have the
   Producer create an Iteration linked to the same
   `work_item_id`, lists input versions and changes, then either produces a new
   Artifact version or performs evidence-only verification. Rerun affected
   checks.
9. **Finish:** accept with evidence and residual risks, or stop/escalate with
   the unresolved reason. Report turns, tool calls, token use, and cost when
   the host exposes them.

Do not continue a loop merely because another round is possible. Stop when the
gate passes, the artifact repair budget is exhausted, evidence cannot be
obtained, the same failure fingerprint repeats without an artifact change, or
authority is required.
