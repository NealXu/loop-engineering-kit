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

Route the task before selecting agents. L0 uses no multi-role loop, L1 uses
Producer/Verifier/Arbiter, L2 adds the read-only Reviewer, and L3 also uses the
read-only Challenger plus human approval before irreversible actions. For L2+,
give the Reviewer the goal, frozen artifact, acceptance criteria, and evidence
without the Producer's rationale.

The installed Skill includes `loop_engineering/cli.py` for `route`, `doctor`,
and `verify`; pass the target project through `--root` for project checks.

The adapter does not grant extra authority. Destructive, production-impacting,
credential-related, and irreversible actions still require explicit approval.
