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
For an installed copy, verify it from its own root with
`python <installed-skill-root>/loop_engineering/cli.py doctor --mode installed
--root <installed-skill-root>`.

1. **Route:** classify the work as L0-L3 from expected file count, risk,
   ambiguity, and irreversibility. From the kit root, use
   `python loop_engineering/cli.py route --risk <level> --files <count>`
   with `--trivial`, `--ambiguous`, or `--irreversible` when applicable.
   The route selects roles, independence, repair budget, and stop conditions.
   L0 is a trivial direct change; L1 adds Verifier; L2 adds independent
   Reviewer; L3 also adds Challenger and human approval before irreversible
   actions.
   Respect the route's `record_depth`:
   - `none`: make the direct change, run one relevant check, and stop. Do not
     read the full protocol, create JSON records, or print a role report.
   - `compact`: read project instructions and only the selected pack. State the
     goal, acceptance criteria, and repair budget in three lines, produce,
     verify, and decide. Skip formal Work Item, Artifact, Finding, Verification,
     Decision, Iteration, and Human Approval records; keep the brief and check
     outcomes in-session. Do not narrate roles unless the project explicitly
     requires it.
   - `full`: continue through the complete loop below. Keep canonical role
     records in-session unless the project explicitly requests persistence.
   - `audited`: continue through the complete loop and persist the required
     machine-readable records.
   The seven JSON objects in `core/artifact-schema/` are canonical records;
   verify JSON/Markdown reports are evidence, not canonical records.
   The numbered Define through Finish steps apply only to full and audited
   routes. A compact route keeps Work Item, Artifact, Verification, and
   Decision information in its brief and check outcomes only.
2. **Define (`full`/`audited`):** read project instructions and
   `core/protocol.md`; select a pack;
   create a Work Item with `id` and `pack_id`; state goal, constraints, risk,
   acceptance criteria as a map of stable criterion IDs to statements, and
   `max_repair_iterations`.
   At the end of Define, write a short run brief with the goal, acceptance
   criteria, current artifact references, open questions, and next action.
   A material open question that can change the goal, acceptance semantics,
   scope, data handling, or irreversible effects blocks `DEFINE -> PRODUCE`.
   Resolve it with the user or an authoritative source, or record an explicit
   assumption and rollback. An independent Reviewer is not a substitute for
   that decision.
3. **Produce:** use `roles/producer.md`; create the smallest complete, versioned
   Artifact linked by `work_item_id`, with a stable `id` and `version`, and
   capture assumptions.
4. **Verify:** use `roles/verifier.md`; run native checks. If the Python
   CLI/config exists, run `python loop_engineering/cli.py verify --root
   <project-root> --report-dir <report-dir>` from the kit root (`python3` on
   Linux, `py -3` on Windows). Use a session-temporary report directory for
   `none`, `compact`, and `full` unless persistent evidence is requested. Use
   an explicit project report directory for `audited`. Link each Verification
   to the tested Artifact id/version and covered `criterion_ids`.
   After frozen canonical records exist, run
   `python loop_engineering/cli.py check-records --dir <records-dir>` to
   resolve record IDs, criteria, versions, Finding recurrences, and
   Artifact/Iteration ancestry.
   For money, numeric aggregation, security, or data-loss logic, add at least
   one boundary or aggregate check beyond the visible happy-path tests.
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
   `next_state: VERIFY`. Include `work_item_id` and `artifact_versions`. For
   `ACCEPT`, include each `criterion_id` mapped to passing
   `verification_ids`; a `REPAIR` records the open findings and failing or
   missing evidence instead. Before `ACCEPT`, run `check-finding` with the
   Work Item, Artifact, and Verification directory for every closed high,
   blocking, or recurring Finding.
8. **Repair:** if required, use the pack workflow and send named findings to the
   Producer. Create an Iteration with the same `work_item_id`, input versions,
   `output_versions`, and changes. Create a new Artifact version or perform
   evidence-only checks and rerun affected checks. Stop at the iteration limit.
   Before repairing, update the run brief with the failing check, changed
   artifact versions, evidence, open findings, and next action. Do not delete
   the original evidence.
9. **Finish:** report artifact versions, exact commands and outcomes, findings,
   residual risks, checks not run, and when available, turns, tool calls, token
   use, and cost. A repeated failure fingerprint with no artifact change stops
   further repair unless new evidence changes the diagnosis.

Use the record shapes in `core/artifact-schema/` when `record_depth` is
`audited`, or when a full run explicitly opts into machine records. Do not add
canonical role-record files to an otherwise unrelated project without a request
or project configuration. An explicitly invoked `verify` writes only the
evidence reports requested by `--report-dir`; omitting that option keeps its
existing project-default behavior. Never fabricate results or treat
BLOCKED/NOT_RUN as PASS. Ask before destructive, irreversible,
production-impacting, or credential-related actions.

Use `migrate-records` for v1/v2 to v3 migration; it defaults to dry-run and
backs up records before `--write`. Use `runtime-checkpoint`, `runtime-status`,
and `runtime-resume` for persistent checkpoints and recovery. For L3, create a
Human Approval with `approve` and reference its id from the final Decision.
Stage 3 operations are `metrics`, `registry-update`/`registry-list`, and
`improvements`; generated candidates require review and are never promoted
automatically.
