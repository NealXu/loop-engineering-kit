# Artifact Schema v2

These JSON Schema files are the canonical inter-role records. They use JSON
Schema 2020-12, use `schema_version: 2`, and contain no host-specific fields.

- `work-item.schema.json`
- `artifact.schema.json`
- `finding.schema.json`
- `verification.schema.json`
- `decision.schema.json`
- `iteration.schema.json`

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

This is a breaking schema upgrade. The repository ships only version 2
schemas; version 1 records need external migration before validation. There is
no automatic migration in Stage 1. General cross-record reference resolution
remains part of the Stage 2 runtime; `check-finding` resolves the regression
Verification IDs required by high, blocking, and recurring findings.

The current Stage 1 contract supports schema-aware tools and manual integration.
Automatic schema validation and durable storage belong to the Stage 2 runtime.
