# Continuous Improvement Workflow

Task iteration repairs the current artifact. Continuous improvement changes the
process itself and therefore needs its own evidence and approval.

1. Aggregate completed run records: rework, failed checks, escaped defects, and
   effective challenges.
2. Identify a repeated pattern and the workflow, role, pack, or check that
   should change.
3. Write a bounded improvement candidate with expected effect and rollback.
4. Evaluate it against historical or fixture cases, including regressions.
5. Obtain independent review and human approval before publishing a rule change.
6. Keep the prior version available.

An agent may propose an improvement but may not silently promote it into global
rules. Stage 3 adds the metrics, version registry, and automation around this
approval process.
