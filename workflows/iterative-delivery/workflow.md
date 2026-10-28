# Iterative Delivery Workflow

Use this workflow for a bounded task that must produce a reviewable result.

1. **Route:** select L0-L3 from expected files, risk, ambiguity, and
   irreversibility. The route determines required roles and the repair budget.
   A trivial L0 change uses the host's direct edit-and-check path.
2. **Define:** create the Work Item with a stable `id` and `pack_id`, assign
   roles, and state the repair budget and risk level.
   Update the run brief with the goal, acceptance criteria, open questions, and
   next action.
3. **Produce:** create an Artifact with the same `work_item_id`, a stable `id`,
   and an explicit `version`; record assumptions.
4. **Verify:** execute the pack's required checks and record each Verification
   against that Artifact `id` and `version`.
5. **Review and challenge:** run only the roles required by the route. For L2+,
   the Reviewer receives the frozen artifact and evidence without the
   Producer's rationale. L3 also uses the Challenger. They may run in parallel
   against the same artifact version.
6. **Reconcile:** deduplicate findings, verify facts, preserve disagreements,
   and separate symptoms from root causes.
7. **Decide:** the Arbiter applies the decision policy and records the
   `work_item_id`, covered `artifact_versions`, evidence, and approver.
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
