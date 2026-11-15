# Artifact Schema v3

These JSON Schema files are the canonical inter-role records. They use JSON
Schema 2020-12, use `schema_version: 3`, and contain no host-specific fields.

- `work-item.schema.json`
- `artifact.schema.json`
- `finding.schema.json`
- `verification.schema.json`
- `decision.schema.json`
- `iteration.schema.json`
- `approval.schema.json`

IDs are stable strings within one run. References between records use those
IDs. Evidence is stored as text that identifies a command result, source,
counterexample, measurement, or human decision; a claim without evidence stays
open.

Artifact identity is `id@version` plus `content_hash`. Compute `content_hash`
as SHA-256 over UTF-8 canonical JSON containing every Artifact field except
`content_hash`: sorted keys, comma/colon separators, and ASCII-escaped strings.
Verification and Human Approval records repeat this digest as
`artifact_content_hash`. Decision `artifact_hashes` maps every declared
`artifact_versions` entry to the matching digest. `check-records` and the
runtime reject a valid-looking but stale hash, including the same
`id@version` being replaced in place.

A `working_tree_change` Artifact additionally records an immutable
`source_revision` and a `file_hashes` map for every path in `files`.
`check-records --repo <git-root>` resolves those files at the recorded revision
and rejects changed or missing content. `base_revision` and `source_revision`
must be Git ancestors of the current `HEAD`; `files` must exactly equal the
`base_revision..source_revision` changed-file set; and every claimed deletion
must be absent at source and in the worktree. A directory exemption is
accepted only when `evidence_path` resolves to the actual records directory
being checked. Other evidence files must stay under the records evidence root,
use JSON or Markdown, and match exact `evidence_hashes`. Verification
execution timestamps require a timezone and cannot precede the locally
attested source revision.

For L3, the Artifact records `producer_context` and final Reviewer/Challenger
PASS records record `host_context` with session id, model, independence, and
`authentication: unverified_host_attestation`. Reviewer and Challenger sessions
must differ from the Producer and from each other. These fields provide
provenance and collision checks; the Kit cannot cryptographically prove that a
host supplied truthful session or model identity.

Work Item `acceptance_criteria` is an object whose keys are stable criterion
IDs and whose values are statements. The kit's JSON loader rejects duplicate
object keys, so a Work Item cannot assign two meanings to one criterion ID.
Every Verification lists one or more `criterion_ids`, and an accepting Decision
maps each
`criterion_id` key to passing `verification_ids`. This removes the v1 practice
of matching criteria by copied prose and prevents duplicate criterion entries.
Decision `evidence_refs` contain stable Finding or Verification IDs; use the
optional `evidence_notes` array for file paths, URLs, and prose. A repaired run
may retain multiple Decisions ordered by `cycle`, with exactly one final ACCEPT
for the final Artifact version. Decision cycles must be unique and strictly
increasing. An ACCEPT that references an Approval also records
`approval_hashes` mapping each referenced Approval ID to the canonical digest
of that Approval record.

A resolved `high` or `blocking` Finding includes a `prevention` object with
`kind`, `action`, and `evidence`. The kinds are ordered `structure`,
`automatic_check`, `skill_rule`, and `human_review`. A repeated finding records
the earlier finding ID in `recurrence_of` and requires prevention in every
status; the same Finding cannot reference itself. Every prevention kind
requires stable `regression_verification_ids`;
non-`structure` prevention also requires `fallback_reason`.

Final Verifier, Reviewer, and Challenger PASS evidence carries `execution`
with the exact command or host-session marker, integer `exit_code`, and an ISO
`executed_at`. Missing execution metadata, or a PASS with non-zero exit code,
does not satisfy Approval or ACCEPT.

Human Approval records a `reviewed_set_digest`: SHA-256 over canonical Work
Item, Artifact, all Findings, and every final-version PASS Verifier, Reviewer,
and Challenger Verification. The final ACCEPT Decision repeats that digest.
Changing a reviewed criterion, Finding, or Verification after approval
invalidates both records.

Evidence that can only exist after the complete record set is valid uses
`closure_gate: true` on both its Finding and Verification. Such Verification
records are excluded from delivery criteria and `reviewed_set_digest` to avoid
a self-referential fixed point. The first pass uses
`check-records --pre-closure`; after that succeeds, closure Verification records
are marked PASS and the same command is rerun without the flag. A closure
Verification can never satisfy a delivery criterion or Reviewer/Challenger gate.

Verification records include a `limitations` array, which may be empty when
there are no material limitations. A Verification used as regression evidence
for a Finding includes `finding_id`; `check-finding` requires it to equal the
Finding id and scans JSON records by `kind`, not by filename prefix.
L2/L3 ACCEPT requires a referenced `role: reviewer` Verification with `PASS`
status on the final Artifact id/version; a reviewer Finding alone is not proof
that the review completed.
L3 also requires final-version Challenger PASS evidence and a referenced
Human Approval record created by the `approve` command for the same Work Item
and Artifact version. Approval records carry
`authentication: unverified_host_attestation`; identity authentication belongs
to the host approval channel.
Each accepted criterion also needs a final-version Verification whose role is
`verifier`. Role-omitted evidence is accepted only for the frozen migration
entry in `migrations/v2-to-v3.json` whose exact canonical record-set digest and
Verification ids match. A `producer` Verification cannot serve as the Verifier
gate.
An open `high` or `blocking` Finding is structurally valid for REPAIR/STOP and
`check-finding`; it blocks only the final ACCEPT decision.

This is a breaking schema upgrade. The repository ships only version 3
schemas. Version 1 and 2 records can be migrated with `migrate-records`; the
command requires explicit Verification role mappings, defaults to dry-run,
validates a complete staged copy, and swaps directories only after validation.
Legacy criterion coverage without an evidence mapping requires explicit
`--record-criteria`; it is never guessed.
Version 3 adds explicit control tiers and route flags, typed evidence
references, Decision cycles, Verification role labels, and Human Approval.
The identity/evidence upgrade is a required in-place v3 maintenance step for
older record sets. Run `migrate-records` to add content hashes, Artifact hashes,
roles, execution metadata, and reviewed-set digests. Roleless legacy evidence
is auto-labelled `verifier` only when it matches the frozen migration manifest;
all other roleless Verification records require explicit
`--verification-role`. Current PASS Verifications lacking execution metadata
require an explicit `--execution-evidence` JSON map; migration never invents a
command, exit code, or execution time.

Iteration records may include `output_versions`; Stage 2 record checks require
it so Artifact ancestry is explicit. Run
`python loop_engineering/cli.py check-records --dir <records-dir>` over frozen
records to resolve IDs, criteria, versions, Finding recurrences, Decisions,
Approvals, and Iteration ancestry. `check-finding` remains the focused
regression-evidence gate for high, blocking, and recurring Findings.
`runtime-checkpoint`, `runtime-status`, and `runtime-resume` provide durable
storage and automatic recovery. `metrics`, `registry-update`, and
`improvements` implement the Stage 3 control-plane operations. A registry key
is the Work Item id plus canonical record digest; a repeated identical entry is
idempotent, while different label, commit, state, version, or approval metadata
for that key is a provenance conflict and cannot overwrite the original.
