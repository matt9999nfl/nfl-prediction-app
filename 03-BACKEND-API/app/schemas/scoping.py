"""
Request and response schemas for the Hypothesis Chat scoping endpoints.

ADR-012.  Nothing here describes an experiment — that is ExperimentCreateRequest's
job, and duplicating it would create a second definition that drifts.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class QuestionOut(BaseModel):
    """One question to put to the user."""
    slot_id: str
    question: str
    type: str
    required: bool
    help: Optional[str] = None
    options_from: Optional[str] = None
    default: Any = None
    # Stage 3.  A pre-fill is never an answer; the UI shows it populated and
    # unconfirmed, and only an explicit answer call commits it.
    prefill: Any = None
    prefill_evidence: Optional[str] = None
    confirmed: bool = False


class SessionCreateRequest(BaseModel):
    hypothesis_text: str = Field(min_length=1)


class AnswerRequest(BaseModel):
    slot_id: str
    value: Any = None


class ApproveRequest(BaseModel):
    """
    The hash the user is approving.

    Required, and compared against the server's own recomputation.  If the two
    disagree the client is looking at a stale brief and approval is refused —
    this is the check that stops "approve one thing, run another".
    """
    config_hash: str = Field(min_length=64, max_length=64)


class SessionStateResponse(BaseModel):
    session_id: str
    hypothesis_text: str
    status: Literal["scoping", "assembled", "approved", "dispatched", "abandoned"]
    answers: dict[str, Any] = Field(default_factory=dict)
    next_question: Optional[QuestionOut] = None
    config: Optional[dict[str, Any]] = None
    config_hash: Optional[str] = None
    approved_hash: Optional[str] = None
    experiment_id: Optional[str] = None
    missing_required: list[str] = Field(default_factory=list)


class BriefResponse(BaseModel):
    session_id: str
    config_hash: str
    brief_markdown: str


class DispatchResponse(BaseModel):
    session_id: str
    experiment_id: str
    run_id: str
    status: str = "running"


class CapabilityGapOut(BaseModel):
    gap_id: str
    session_id: Optional[str] = None
    requested_concept: str
    why_unavailable: str
    nearest_expressible: Optional[str] = None
    suggested_definition: Optional[str] = None
    status: str
    created_at: Optional[str] = None


class CapabilityGapListResponse(BaseModel):
    data: list[CapabilityGapOut]


class ConcernOut(BaseModel):
    severity: Literal["high", "medium", "low"]
    kind: str
    message: str


class ReviewResponse(BaseModel):
    """
    The governor's read on whether this experiment is worth running.

    Advisory. Nothing in the dispatch path consults it — a governor with a veto
    becomes a thing to route around, and the honest signal goes with the veto.
    """
    session_id: str
    verdict: Literal["proceed", "proceed_with_caution", "reconsider"]
    concerns: list[ConcernOut] = Field(default_factory=list)
    evaluated_games: Optional[int] = None
    slice_fraction: Optional[float] = None
    advisory_only: bool = True


class PrefillOut(BaseModel):
    """
    A proposed answer, NOT an answer.

    It reaches the UI attached to a question that still gets asked, carrying the
    words from the hypothesis that produced it. Only an explicit call to
    /answers commits it. ADR-012 — the difference between "it guessed and moved
    on" and "it guessed and showed you".
    """
    slot_id: str
    value: Any = None
    confidence: Optional[float] = None
    evidence_quote: Optional[str] = None
    confirmed: bool = False


class ExtractResponse(BaseModel):
    session_id: str
    prefills: list[PrefillOut] = Field(default_factory=list)
    gaps: list[CapabilityGapOut] = Field(default_factory=list)
    # True when ANTHROPIC_API_KEY is unset or the call failed. The session is
    # still completable — every question simply gets asked normally.
    extraction_unavailable: bool = False
    detail: Optional[str] = None
