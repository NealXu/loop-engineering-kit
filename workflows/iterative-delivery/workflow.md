# Iterative Delivery Workflow

Use this workflow for a bounded task that must produce a reviewable result.

1. **Define:** create the Work Item with a stable `id` and `pack_id`, assign
   roles, and state the repair budget and risk level.
2. **Produce:** create an Artifact with the same `work_item_id`, a stable `id`,
   and an explicit `version`; record assumptions.
3. **Verify:** execute the pack's required checks and record each Verification
   against that Artifact `id` and `version`.
4. **Review and challenge:** assign independent Reviewer and Challenger duties;
   they may run in parallel against the same artifact version.
5. **Reconcile:** deduplicate findings, verify facts, preserve disagreements,
   and separate symptoms from root causes.
6. **Decide:** the Arbiter applies the decision policy and records the
   `work_item_id`, covered `artifact_versions`, evidence, and approver.
7. **Repair:** the Producer creates an Iteration linked to the same
   `work_item_id`, lists input versions and changes, then either produces a new
   Artifact version or performs evidence-only verification. Rerun affected
   checks.
8. **Finish:** accept with evidence and residual risks, or stop/escalate with
   the unresolved reason.

Do not continue a loop merely because another round is possible. Stop when the
gate passes, the artifact repair budget is exhausted, evidence cannot be
obtained, or authority is required.
