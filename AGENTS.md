# Agent Guidance
- For non-trivial work, follow `core/protocol.md` and invoke the `loop-engineering` Skill.
- Select the appropriate workflow pack; software changes use `packs/software-development/`.
- Producer edits artifacts; Reviewer and Challenger are read-only; Verifier records evidence; Arbiter applies the gate.
- Never claim an unexecuted check passed. Mark unavailable checks BLOCKED/NOT_RUN.
- Default maximum repair limit is 3. Preserve unrelated changes.
- Ask before destructive, irreversible, production-impacting, or credential-related actions.
