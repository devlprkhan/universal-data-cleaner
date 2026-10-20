"""Structured records of what the cleaner learned and decided."""

from __future__ import annotations

from dataclasses import dataclass

DECISION_COLUMNS = ["column", "action", "reason", "source", "before", "after"]


@dataclass(frozen=True, slots=True)
class CleaningDecision:
    """A single auditable cleaning decision.

    Parameters
    ----------
    column:
        Source column the decision applies to, or ``"*"`` for frame-level
        decisions such as contract inference.
    action:
        Short, machine-readable verb, for example ``"impute"``,
        ``"cap_outliers"``, ``"expand_datetime"`` or ``"drop_column"``.
    reason:
        Human-readable explanation of why the action was taken.
    source:
        Where the rule came from: ``"learned"`` (learned from training data),
        ``"config"`` (explicit :class:`CleanerConfig`), ``"contract"`` (column
        contract) or ``"default"`` (library default/inference).
    before:
        Optional description of the state before the decision.
    after:
        Optional description of the state after the decision.
    """

    column: str
    action: str
    reason: str
    source: str
    before: object = None
    after: object = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the decision."""
        return {
            "column": self.column,
            "action": self.action,
            "reason": self.reason,
            "source": self.source,
            "before": self.before,
            "after": self.after,
        }
