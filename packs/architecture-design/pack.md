# Architecture Design Pack

## Role Binding

| Generic role | Domain role |
|---|---|
| Producer | Architect |
| Verifier | Cost, capacity, or evidence analyst |
| Reviewer | Independent architecture reviewer |
| Challenger | Red team |
| Arbiter | Decision maker |

## Required Artifacts

- Candidate architecture and scope.
- Tradeoff analysis with explicit assumptions.
- Capacity and operating-cost estimate where relevant.
- Failure, recovery, security, and scalability risk register.
- Verification evidence for measurable claims.
- Architecture Decision Record with accepted residual risks.

## Acceptance

- Business constraints and non-goals are explicit.
- Each major decision has alternatives and evidence.
- Single points of failure, recovery objectives, and capacity limits are
  addressed.
- Cost assumptions identify their source and uncertainty.
- Unvalidated claims are labelled and assigned an owner instead of presented as
  facts.

## Challenge Focus

Wrong problem framing, hidden operational cost, recovery gaps, capacity cliffs,
vendor lock-in, and alternatives that are cheaper, safer, or more reversible.
