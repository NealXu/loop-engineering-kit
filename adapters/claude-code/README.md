# Claude Code Adapter

Claude Code maps each role to a project or user subagent in `.claude/agents/`.

- `producer.md`: writes and repairs artifacts.
- `verifier.md`: executes checks and records evidence.
- `reviewer.md`: performs independent read-only review.
- `challenger.md`: challenges goals, assumptions, and failure paths.
- `arbiter.md`: applies acceptance and records the decision.

The loop-engineering Skill is the Controller entry point. If the host cannot
provide an independent subagent, the Controller may perform the duty in-session
but must label it as non-independent.

The adapter does not grant extra authority. Destructive, production-impacting,
credential-related, and irreversible actions still require explicit approval.
