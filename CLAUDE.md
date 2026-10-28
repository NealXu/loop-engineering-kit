# Claude Code Guidance
Use the `loop-engineering` Skill for non-trivial work and follow `core/protocol.md`.
Run the Skill's route step first. L0 bypasses the multi-role loop; L1 uses
Producer, Verifier, and Arbiter; L2 adds an independent Reviewer; L3 adds
Challenger and human approval before irreversible actions.
Select a workflow pack; software changes use `packs/software-development/`.
Producer edits artifacts, Verifier records evidence, Reviewer and Challenger are read-only, and Arbiter applies the acceptance gate.
For L2+, invoke the named read-only Reviewer through Claude Code's subagent
mechanism and give it the frozen artifact, acceptance criteria, and evidence,
not the Producer's explanation. If a separate session is unavailable, disclose
that the review was not independent.
Never fabricate results or overwrite unrelated changes. Ask before destructive or production-impacting actions.
