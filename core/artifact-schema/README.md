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
increasing; a `CONTINUE` Iteration may remain undecided.

A resolved `high` or `blocking` Finding includes a `prevention` object with
`kind`, `action`, and `evidence`. The kinds are ordered `structure`,
`automatic_check`, `skill_rule`, and `human_review`. A repeated finding records
the earlier finding ID in `recurrence_of` and requires prevention in every
status; the same Finding cannot reference itself. Every prevention kind
requires stable `regression_verification_ids`;
non-`structure` prevention also requires `fallback_reason`.

Verification records include a `limitations` array, which may be empty when
there are no material limitations. A Verification used as regression evidence
for a Finding includes `finding_id`; `check-finding` requires it to equal the
Finding id and scans JSON records by `kind`, not by filename prefix.
L2/L3 ACCEPT requires a referenced `role: reviewer` Verification with `PASS`
status on the final Artifact id/version; a reviewer Finding alone is not proof
that the review completed.
L3 also requires final-version Challenger PASS evidence and a referenced
Human Approval record created by the `approve` command for the same Work Item
and Artifact version.
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

Iteration records may include `output_versions`; Stage 2 record checks require
it so Artifact ancestry is explicit. Run
`python loop_engineering/cli.py check-records --dir <records-dir>` over frozen
records to resolve IDs, criteria, versions, Finding recurrences, Decisions,
Approvals, and Iteration ancestry. `check-finding` remains the focused
regression-evidence gate for high, blocking, and recurring Findings.
`runtime-checkpoint`, `runtime-status`, and `runtime-resume` provide durable
storage and automatic recovery. `metrics`, `registry-update`, and
`improvements` implement the Stage 3 control-plane operations.
