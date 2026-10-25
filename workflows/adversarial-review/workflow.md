# Adversarial Review Workflow

Use this workflow when the main risk is choosing the wrong target, assumption,
or design rather than missing a routine check.

1. Freeze an artifact version.
2. Give Reviewer and Challenger the Work Item and artifact without the
   Producer's defense.
3. Require each finding to name evidence, impact, and a falsifying method.
4. Run bounded experiments where disagreement can be settled with evidence.
5. Preserve unresolved disagreement rather than forcing consensus.
6. Send confirmed high-impact findings to repair, or escalate the unresolved
   risk to the Arbiter.

Reviewer focus: defects in the current artifact. Challenger focus: whether the
goal, constraints, assumptions, or selected approach are wrong.
