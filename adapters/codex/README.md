# Codex Adapter

Codex maps each role to a project or user subagent in `.codex/agents/`.

- `producer.toml`: writes and repairs artifacts.
- `verifier.toml`: executes checks and records evidence.
- `reviewer.toml`: performs independent read-only review.
- `challenger.toml`: challenges goals, assumptions, and failure paths.
- `arbiter.toml`: applies acceptance and records the decision.

The loop-engineering Skill is the Controller entry point. When the host cannot
provide an independent subagent, the Controller may perform the duty in-session
but must disclose that the review was not independent.

The adapter does not grant extra authority. Destructive, production-impacting,
credential-related, and irreversible actions still require explicit approval.
