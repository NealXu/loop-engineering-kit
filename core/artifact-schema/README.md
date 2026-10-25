# Artifact Schema v1

These JSON Schema files are the canonical inter-role records. They use JSON
Schema 2020-12 and contain no host-specific fields.

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

The current Stage 1 contract supports schema-aware tools and manual integration.
Automatic schema validation and durable storage belong to the Stage 2 runtime.
