"""
The scoping state machine.

Pure: given a tree and the answers so far, decide what to ask next and what
state the session is in.  No BigQuery, no Claude, no I/O.

This is the rule-engine half of ADR-012 commitment 2 — the 30% layer in the
plan's 60/30/10 split.  It asks questions in a fixed, testable order and makes
no judgments.  Judgment lives in the governor (Stage 4) and does not belong
here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.scoping.assemble import assemble, missing_required, record_only_answers
from app.scoping.schema import ScopingTree, Slot

# Session lifecycle.  Matches platform.scoping_sessions.status.
STATUS_SCOPING = "scoping"
STATUS_ASSEMBLED = "assembled"
STATUS_APPROVED = "approved"
STATUS_DISPATCHED = "dispatched"
STATUS_ABANDONED = "abandoned"


class SlotNotInTree(KeyError):
    """An answer arrived for a slot the tree does not declare."""


@dataclass(frozen=True)
class PendingQuestion:
    """One question to put to the user, with everything the UI needs."""

    slot_id: str
    question: str
    type: str
    required: bool
    help: Optional[str]
    options_from: Optional[str]
    default: Any
    # Set once Stage 3 exists.  A pre-filled value is NEVER an answer — the
    # question is still asked, arriving populated, and only an explicit
    # confirmation moves it into `answers`.  See ADR-012.
    prefill: Any = None
    prefill_evidence: Optional[str] = None

    @classmethod
    def from_slot(cls, slot: Slot) -> "PendingQuestion":
        return cls(
            slot_id=slot.id,
            question=slot.question,
            type=slot.type,
            required=slot.required,
            help=slot.help,
            options_from=slot.options_from,
            default=slot.default,
        )


def next_question(tree: ScopingTree, answers: dict[str, Any]) -> Optional[PendingQuestion]:
    """
    The next slot to ask, in the tree's declared order.

    Optional slots are asked too — skipping them is a choice the user makes by
    answering null, not one the engine makes for them.  Returns None when every
    slot has been put to the user.
    """
    for slot in tree.slots:
        if slot.id not in answers:
            return PendingQuestion.from_slot(slot)
    return None


def apply_answer(
    tree: ScopingTree,
    answers: dict[str, Any],
    slot_id: str,
    value: Any,
) -> dict[str, Any]:
    """
    Return a NEW answers dict with `slot_id` set.

    Does not mutate its argument — the caller persists the result, so a failed
    write must not leave the in-memory state ahead of the stored state.
    """
    try:
        tree.by_id(slot_id)
    except KeyError:
        raise SlotNotInTree(slot_id) from None
    updated = dict(answers)
    updated[slot_id] = value
    return updated


def is_complete(tree: ScopingTree, answers: dict[str, Any]) -> bool:
    """True when every slot has been put to the user and nothing required is blank."""
    return next_question(tree, answers) is None and not missing_required(tree, answers)


def build(tree: ScopingTree, answers: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    (config payload, record-only answers) for a complete session.

    Raises IncompleteScopingError via assemble() if anything required is blank.
    """
    return assemble(tree, answers), record_only_answers(tree, answers)
