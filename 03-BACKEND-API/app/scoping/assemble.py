"""
Slot answers → an ExperimentCreateRequest payload.

Pure.  No BigQuery, no Claude, no clock, no randomness — the same answers
always produce the same payload, which is what makes the approval hash
meaningful.

Record-only slots (binds_to = None) are deliberately NOT assembled into the
config.  They are carried separately and rendered into the brief; see render.py.
"""
from __future__ import annotations

from typing import Any

from app.scoping.schema import ScopingTree, Slot


class IncompleteScopingError(Exception):
    """Raised when a required slot has no answer."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"unanswered required slot(s): {', '.join(missing)}")


def missing_required(tree: ScopingTree, answers: dict[str, Any]) -> list[str]:
    """Ids of required slots — config and record-only alike — with no answer."""
    return [
        s.id
        for s in tree.slots
        if s.required and answers.get(s.id, None) is None
    ]


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cursor = target
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def _effective(slot: Slot, answers: dict[str, Any]) -> Any:
    """The answer if given, else the slot's declared default."""
    if slot.id in answers and answers[slot.id] is not None:
        return answers[slot.id]
    return slot.default


def assemble(tree: ScopingTree, answers: dict[str, Any]) -> dict[str, Any]:
    """
    Build the request payload from answers.

    Raises IncompleteScopingError if any required slot is unanswered — an
    incomplete config must never reach a hash, because hashing it would make it
    approvable.
    """
    missing = missing_required(tree, answers)
    if missing:
        raise IncompleteScopingError(missing)

    payload: dict[str, Any] = {}
    for slot in tree.config_slots:
        value = _effective(slot, answers)
        # An optional slot left blank with no default is omitted entirely so
        # Pydantic applies the model's own default, rather than being written
        # as an explicit null which some fields would reject.
        if value is None and not slot.required:
            continue
        _set_path(payload, slot.binds_to, value)
    return payload


def record_only_answers(tree: ScopingTree, answers: dict[str, Any]) -> dict[str, Any]:
    """The answers that no config field holds — kept for the brief and governor."""
    return {
        s.id: answers.get(s.id)
        for s in tree.record_only_slots
        if answers.get(s.id) is not None
    }
