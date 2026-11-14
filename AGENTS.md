# Agent Guidance
- For non-trivial work, invoke the `loop-engineering` Skill and follow
  `core/protocol.md`.
- Route first: L0 is a trivial direct change; L1 uses Producer, Verifier, and
  Arbiter; L2 adds an independent Reviewer; L3 adds Challenger and human
  approval before irreversible actions.
- Respect `record_depth`: no formal records for L0, a compact brief for L1,
  an in-session full loop for L2, and persisted canonical role records only
  for L3 or an explicit project request. Explicitly invoked verify
  JSON/Markdown reports are evidence, not canonical role records. A persistence
  request does not override compact; re-route the task as full or audited.
- Select the appropriate workflow pack; software changes use `packs/software-development/`.
- Producer edits artifacts; Reviewer and Challenger are read-only; Verifier records evidence; Arbiter applies the gate.
- Never claim an unexecuted check passed. Mark unavailable checks BLOCKED/NOT_RUN.
- Keep the route-assigned repair budget. Stop when the same failure fingerprint
  recurs without new evidence. Preserve unrelated changes.
- Ask before destructive, irreversible, production-impacting, or credential-related actions.
