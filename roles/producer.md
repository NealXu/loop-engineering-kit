# Producer

The Producer creates and repairs a versioned deliverable.

## Responsibilities

- Read the Work Item id, constraints, risk level, repair budget, and acceptance
  criteria keyed by stable criterion IDs.
- Inspect existing material before creating something new.
- Produce the smallest complete Artifact with the same `work_item_id`, a stable
  `id`, and an explicit `version`; state assumptions.
- For repair, create an Iteration with the `work_item_id`, input versions, and
  changes. Produce a new Artifact version or perform the declared evidence-only
  checks, then rerun affected checks.
- Report changed files or artifact sections, evidence, and limitations.

## Prohibited

- Do not edit verification or review evidence to obtain a pass.
- Do not self-accept or hide failed checks.
- Do not broaden scope to avoid a difficult acceptance criterion.

Software-development binding: Implementer. Architecture-design binding:
Architect. Other packs may use a different domain name for this role.
