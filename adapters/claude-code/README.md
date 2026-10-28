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

Route the task before selecting agents. L0 uses no multi-role loop, L1 uses
Producer/Verifier/Arbiter, L2 adds the read-only Reviewer, and L3 also uses the
read-only Challenger plus human approval before irreversible actions. For L2+,
invoke the named Reviewer and give it the goal, frozen artifact, acceptance
criteria, and evidence rather than the Producer's rationale.

The user-level installation includes `loop_engineering/cli.py` beside the
Skill. Use `route` before work and `doctor --mode project --root <project>` /
`verify --root <project>` when a project configuration exists.

The adapter does not grant extra authority. Destructive, production-impacting,
credential-related, and irreversible actions still require explicit approval.
