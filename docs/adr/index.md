# Architecture decisions

Architecture decision records (ADRs) capture decisions that affect the public
API, compatibility, safety guarantees, or release process. Each record states the
context, the decision, and its consequences.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-production-hardening-strategy.md) | Prioritize production hardening over new data primitives | Accepted |

## When to add an ADR

Add one when a change:

- adds or changes a public API;
- changes a safety guarantee or a documented default;
- changes artifact compatibility or serialization;
- changes the release or verification process;
- introduces an optional dependency or integration boundary.

Small internal refactors and documentation fixes do not need an ADR.

## Format

Use a short Markdown file named `NNNN-short-title.md` with these sections:

- Status
- Context
- Decision
- Consequences
- Verification (when the decision has testable outcomes)

Update the status to `Superseded` and link the replacement when a decision
changes.
