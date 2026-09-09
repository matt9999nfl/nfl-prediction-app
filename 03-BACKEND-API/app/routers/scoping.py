"""
Hypothesis Chat — scoping endpoints (Stage 2, deterministic core).

ADR-012.  There is NO model call anywhere in this module: the whole flow below
works with ANTHROPIC_API_KEY unset, and a test asserts that.  Stage 3 and 4 add
pre-fills and a governor verdict on top; neither is required to reach a run.

Dispatch calls `create_experiment` and `trigger_run` — the existing wizard
handlers — rather than writing to BigQuery itself.  That is the structural form
of "the chat cannot do more than the wizard": it is not permitted to do less or
more, it literally runs the same code.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.cloud import bigquery

from app.claude_scoping import ClaudeScopingError, extract_slots
from app.config import settings
from app.dependencies import get_bq_client, get_request_id, require_api_key
from app.queries import features as fq
from app.queries import scoping as sq
from app.routers.experiments import create_experiment, trigger_run
from app.schemas.common import ErrorResponse
from app.schemas.experiments import ExperimentCreateRequest
from app.schemas.scoping import (
    AnswerRequest,
    ApproveRequest,
    ApproveRequest as _ApproveRequest,  # noqa: F401  (kept for clarity in signatures)
    BriefResponse,
    CapabilityGapListResponse,
    DispatchDryRunResponse,
    DispatchResponse,
    ExtractResponse,
    PrefillOut,
    ReviewResponse,
    QuestionOut,
    SessionCreateRequest,
    SessionStateResponse,
)
from app.scoping import session as sm
from app.scoping.assemble import IncompleteScopingError, missing_required
from app.scoping import governor
from app.scoping.gaps import detect_gaps
from app.scoping.hashing import approval_hash, config_hash
from app.scoping.render import render
from app.scoping.schema import load_tree

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scoping", tags=["scoping"])


def _err(status: int, message: str, code: str, request_id: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": message, "code": code, "request_id": request_id},
    )


def _load_or_404(bq, session_id: str, request_id: str) -> dict:
    try:
        row = sq.get_session(bq, session_id)
    except Exception as exc:
        logger.error("[%s] BigQuery error loading session %s: %s", request_id, session_id, exc, exc_info=True)
        raise _err(502, "Upstream query failed", "upstream_error", request_id)
    if row is None:
        raise _err(404, f"Scoping session '{session_id}' not found", "not_found", request_id)
    return row


def _state(row: dict) -> SessionStateResponse:
    tree = load_tree()
    answers = row.get("slot_answers") or {}
    q = sm.next_question(tree, answers)
    return SessionStateResponse(
        session_id=row["session_id"],
        hypothesis_text=row["hypothesis_text"],
        status=row["status"],
        answers=answers,
        next_question=QuestionOut(**q.__dict__) if q else None,
        config=row.get("config"),
        config_hash=row.get("config_hash"),
        approved_hash=row.get("approved_hash"),
        experiment_id=row.get("experiment_id"),
        missing_required=missing_required(tree, answers),
    )


# ── POST /api/v1/scoping/sessions ────────────────────────────────────────────


@router.post("/sessions", response_model=SessionStateResponse, status_code=201,
             responses={401: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
             summary="Start a scoping session from a plain-English hypothesis")
def start_session(
    body: SessionCreateRequest,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> SessionStateResponse:
    session_id = str(uuid.uuid4())
    try:
        sq.create_session(bq, session_id, body.hypothesis_text)
    except Exception as exc:
        logger.error("[%s] BigQuery error creating scoping session: %s", request_id, exc, exc_info=True)
        raise _err(502, "Upstream query failed", "upstream_error", request_id)

    logger.info("[%s] Started scoping session %s", request_id, session_id)
    return _state(
        {
            "session_id": session_id,
            "hypothesis_text": body.hypothesis_text,
            "status": "scoping",
            "slot_answers": {},
            "config": None,
            "config_hash": None,
            "approved_hash": None,
            "experiment_id": None,
        }
    )


@router.get("/sessions/{session_id}", response_model=SessionStateResponse,
            responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                       502: {"model": ErrorResponse}},
            summary="Current state of a scoping session")
def get_session_state(
    session_id: str,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> SessionStateResponse:
    """
    Requires the API key.  A session carries the hypothesis, every answer and
    the assembled config — unpublished research thinking, readable by anyone
    holding the uuid while this was open.  The project's open-read convention
    exists for the public predictions surface, which is data meant to be shown;
    this is not that.  PROJECT-LEAD ruling HC-S6 Q3.
    """
    return _state(_load_or_404(bq, session_id, request_id))


# ── POST /api/v1/scoping/sessions/{id}/answers ───────────────────────────────


@router.post("/sessions/{session_id}/answers", response_model=SessionStateResponse,
             responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                        409: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
             summary="Answer one slot and advance")
def answer_slot(
    session_id: str,
    body: AnswerRequest,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> SessionStateResponse:
    row = _load_or_404(bq, session_id, request_id)

    if row["status"] == "dispatched":
        raise _err(409, "This session has already been dispatched", "already_dispatched", request_id)

    tree = load_tree()
    try:
        answers = sm.apply_answer(tree, row.get("slot_answers") or {}, body.slot_id, body.value)
    except sm.SlotNotInTree:
        raise _err(400, f"Unknown slot '{body.slot_id}'", "unknown_slot", request_id)

    # Assemble as soon as it is possible to.  An answer that changes the config
    # necessarily changes the hash, which invalidates any prior approval —
    # approved_hash is cleared so approval must be given again.
    payload = None
    chash = None
    status = "scoping"
    if sm.is_complete(tree, answers):
        try:
            payload, _ro = sm.build(tree, answers)
        except IncompleteScopingError:
            payload = None
        if payload is not None:
            try:
                ExperimentCreateRequest.model_validate(payload)
            except Exception as exc:
                raise _err(400, f"Answers do not form a valid experiment: {exc}", "invalid_config", request_id)
            chash = config_hash(payload)
            status = "assembled"

    try:
        sq.update_answers(bq, session_id, answers, payload, chash, status)
    except Exception as exc:
        logger.error("[%s] BigQuery error saving answers for %s: %s", request_id, session_id, exc, exc_info=True)
        raise _err(502, "Upstream query failed", "upstream_error", request_id)

    # Re-read rather than patch the row in memory.  FINDING HC-S6-F1: this used
    # to assign approved_hash=None to the response dict while the UPDATE left
    # the column alone, so the API reported a cleared approval that storage
    # still held.  The response now says what the row says, and if the two ever
    # disagree again the endpoint reports the disagreement instead of hiding it.
    return _state(_load_or_404(bq, session_id, request_id))


# ── GET /api/v1/scoping/sessions/{id}/brief ──────────────────────────────────


@router.get("/sessions/{session_id}/brief", response_model=BriefResponse,
            responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                       409: {"model": ErrorResponse}},
            summary="The brief, rendered from the exact config that will run")
def get_brief(
    session_id: str,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> BriefResponse:
    row = _load_or_404(bq, session_id, request_id)
    tree = load_tree()
    answers = row.get("slot_answers") or {}

    try:
        payload, record_only = sm.build(tree, answers)
    except IncompleteScopingError as exc:
        raise _err(409, str(exc), "incomplete_scoping", request_id)

    return BriefResponse(
        session_id=session_id,
        config_hash=config_hash(payload),
        approval_hash=approval_hash(payload, record_only),
        brief_markdown=render(
            payload,
            hypothesis_text=row["hypothesis_text"],
            record_only=record_only,
            tree=tree,
        ),
    )


# ── POST /api/v1/scoping/sessions/{id}/approve ───────────────────────────────


@router.post("/sessions/{session_id}/approve", response_model=SessionStateResponse,
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
             summary="Approve the brief by its config hash")
def approve(
    session_id: str,
    body: ApproveRequest,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> SessionStateResponse:
    row = _load_or_404(bq, session_id, request_id)
    tree = load_tree()

    try:
        payload, record_only = sm.build(tree, row.get("slot_answers") or {})
    except IncompleteScopingError as exc:
        raise _err(409, str(exc), "incomplete_scoping", request_id)

    actual = config_hash(payload)
    if body.config_hash != actual:
        # The client approved a brief that no longer matches the answers.
        raise _err(
            409,
            "The brief you approved is out of date — an answer changed since it "
            "was rendered. Re-read the brief and approve again.",
            "stale_brief",
            request_id,
        )

    # What gets STORED covers everything render() puts in the brief: the config
    # and the record-only answers.  FINDING HC-S6-F2 — the config hash alone
    # left mechanism, falsifier and prior_attempts free to change after
    # approval without moving it, so dispatch could proceed against a document
    # nobody signed off.  ADR-012 commitment 3: the approved artefact and the
    # executed artefact cannot differ.
    approved = approval_hash(payload, record_only)
    if body.approval_hash is not None and body.approval_hash != approved:
        # The client read a brief whose record-only half has since changed —
        # the falsifier, say. config_hash cannot see that, which is the window
        # HC-S6-FIX-Q5 describes. A client that sends the brief's approval_hash
        # closes it here rather than discovering it at dispatch.
        raise _err(
            409,
            "The brief you approved is out of date — an answer changed since it "
            "was rendered. Re-read the brief and approve again.",
            "stale_brief",
            request_id,
        )

    try:
        written = sq.set_approved_hash(bq, session_id, approved, expected_config_hash=actual)
    except Exception as exc:
        logger.error("[%s] BigQuery error approving %s: %s", request_id, session_id, exc, exc_info=True)
        raise _err(502, "Upstream query failed", "upstream_error", request_id)

    if written is False:
        # FINDING HC-S6-F10.  The conditional write matched no row, so an answer
        # landed between the load above and the write.  Saying so beats
        # attaching an approval to answers it was not computed from and leaving
        # dispatch to refuse it later with nothing to explain why.
        raise _err(
            409,
            "An answer changed while this approval was being recorded, so it was "
            "not applied. Re-read the brief and approve again.",
            "approval_conflict",
            request_id,
        )

    return _state(_load_or_404(bq, session_id, request_id))


# ── POST /api/v1/scoping/sessions/{id}/dispatch ──────────────────────────────


@router.post("/sessions/{session_id}/dispatch", response_model=None,
             status_code=202,
             responses={200: {"model": DispatchDryRunResponse},
                        202: {"model": DispatchResponse},
                        401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                        409: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
             summary="Create the experiment and start the run")
def dispatch(
    session_id: str,
    request: Request,
    response: Response,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
    dry_run: bool = False,
) -> DispatchResponse | DispatchDryRunResponse:
    """
    `?dry_run=true` runs every check below and then stops, returning the exact
    payload it would have sent to create_experiment.  It creates no experiment,
    fires no runner job, and writes nothing — 200 rather than 202, because
    nothing was accepted for processing.

    Ruled in HC-S6 Q2: without it, the most consequential path in the feature
    could only be exercised by minting a real experiment and firing the
    production runner, so it was never exercised at all.  A guarantee that
    cannot be rehearsed is a guarantee nobody has checked.
    """
    row = _load_or_404(bq, session_id, request_id)

    if row["status"] == "dispatched":
        raise _err(409, "This session has already been dispatched", "already_dispatched", request_id)

    tree = load_tree()
    try:
        payload, record_only = sm.build(tree, row.get("slot_answers") or {})
    except IncompleteScopingError as exc:
        raise _err(409, str(exc), "incomplete_scoping", request_id)

    # THE GUARANTEE.  Recomputed from the answers as they are right now, and
    # compared against what was approved.  Not read from config_hash — a stored
    # value could have been written by anything.
    #
    # The comparison is against the hash of the WHOLE brief (config plus the
    # record-only answers), because that is the document that was approved.
    # FINDING HC-S6-F2.
    actual = config_hash(payload)
    recomputed = approval_hash(payload, record_only)
    approved = row.get("approved_hash")
    if not approved:
        raise _err(409, "This experiment has not been approved", "not_approved", request_id)
    if approved != recomputed:
        raise _err(
            409,
            "The brief changed after approval and will not be run. Re-read the "
            "brief and approve the current version.",
            "approval_mismatch",
            request_id,
        )

    body = ExperimentCreateRequest.model_validate(payload)

    if dry_run:
        logger.info("[%s] Dry-run dispatch for session %s passed every check", request_id, session_id)
        response.status_code = 200
        return DispatchDryRunResponse(
            session_id=session_id,
            config_hash=actual,
            approved_hash=approved,
            would_create=body.model_dump(mode="json"),
        )

    # Same handlers the wizard uses — not a parallel write path.
    created = create_experiment(
        body=body, request=request, request_id=request_id, bq=bq, _=None
    )
    run = trigger_run(
        experiment_id=created.experiment_id, request=request,
        request_id=request_id, bq=bq, _=None,
    )

    try:
        sq.mark_dispatched(bq, session_id, created.experiment_id)
    except Exception as exc:
        # The experiment exists and is running; losing the link is bad but not
        # worth failing the request over. Log loudly.
        logger.error("[%s] Dispatched %s but failed to link session %s: %s",
                     request_id, created.experiment_id, session_id, exc, exc_info=True)

    logger.info("[%s] Session %s dispatched as experiment %s (run %s)",
                request_id, session_id, created.experiment_id, run.run_id)
    return DispatchResponse(
        session_id=session_id, experiment_id=created.experiment_id, run_id=run.run_id
    )


# ── GET /api/v1/scoping/sessions/{id}/review ─────────────────────────────────


@router.get("/sessions/{session_id}/review", response_model=ReviewResponse,
            responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                       409: {"model": ErrorResponse}},
            summary="Whether this experiment is worth running (advisory)")
def review_session(
    session_id: str,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> ReviewResponse:
    """
    The governance layer. Every check behind it is deterministic — sample size,
    duplication, cold start and threshold plausibility are arithmetic, so they
    are done as arithmetic rather than asked of a model that might answer
    "looks good" on the day it matters.

    Read-only and advisory. `dispatch` does not call this.
    """
    row = _load_or_404(bq, session_id, request_id)
    tree = load_tree()

    try:
        config, record_only = sm.build(tree, row.get("slot_answers") or {})
    except IncompleteScopingError as exc:
        raise _err(409, str(exc), "incomplete_scoping", request_id)

    methodology = config.get("methodology") or {}

    # Real counts where they can be had.  An input that cannot be loaded is
    # recorded by name and reported — FINDING HC-S6-F6.  This used to log a
    # warning and carry on with fraction=None and priors=[], which returns a
    # 200 with an empty concern list: the same shape as a healthy review of a
    # sound experiment, having checked nothing, and degrading toward a LARGER
    # apparent sample. A check that could not run is not a check that passed.
    unavailable: dict[str, str] = {}

    fraction = None
    try:
        fraction = sq.slice_fraction(
            bq,
            start_season=methodology.get("start_season"),
            end_season=methodology.get("end_season"),
            game_universe=methodology.get("game_universe"),
        )
    except Exception as exc:
        logger.error("[%s] Could not count slice for %s: %s", request_id, session_id, exc, exc_info=True)
        unavailable["slice_fraction"] = str(exc) or exc.__class__.__name__

    priors: list = []
    try:
        priors = sq.list_prior_configs(bq)
    except Exception as exc:
        logger.error("[%s] Could not load prior configs for %s: %s", request_id, session_id, exc, exc_info=True)
        unavailable["prior_configs"] = str(exc) or exc.__class__.__name__

    result = governor.review(
        config,
        record_only=record_only,
        prior_configs=priors,
        slice_fraction=fraction,
        current_season=settings_current_season(),
        unavailable_inputs=unavailable,
    )

    return ReviewResponse(
        session_id=session_id,
        verdict=result["verdict"],
        concerns=result["concerns"],
        evaluated_games=governor.evaluated_games(methodology),
        slice_fraction=fraction,
        checks_unavailable=sorted(unavailable),
        degraded=bool(unavailable),
    )


def settings_current_season() -> int:
    """
    The NFL season a date falls in — seasons are named for the year they start,
    and run into the following February, so anything before March belongs to the
    previous year's season.
    """
    from datetime import date
    today = date.today()
    return today.year - 1 if today.month < 3 else today.year


# ── POST /api/v1/scoping/sessions/{id}/extract ───────────────────────────────


def _filterable_fields() -> set[str]:
    """
    The fields GameUniverseFilter accepts, read from the schema itself.

    Never hardcoded: when the filter is widened, gap detection stops reporting
    those slices as gaps automatically, with no edit here.
    """
    from app.schemas.experiments import GameUniverseFilter
    return set(GameUniverseFilter.model_fields["field"].annotation.__args__)


@router.post("/sessions/{session_id}/extract", response_model=ExtractResponse,
             responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
             summary="Propose slot pre-fills from the hypothesis, and record what cannot be expressed")
def extract(
    session_id: str,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> ExtractResponse:
    """
    Optional step. Everything here is additive: if it is unavailable, the
    session still completes by answering every question normally, which is
    what makes Stage 2 the load-bearing layer rather than this one.
    """
    row = _load_or_404(bq, session_id, request_id)
    tree = load_tree()

    try:
        catalog_raw = fq.list_features(bq)
    except Exception as exc:
        logger.error("[%s] Could not load feature catalog: %s", request_id, exc, exc_info=True)
        raise _err(502, "Upstream query failed", "upstream_error", request_id)

    catalog = [
        {"column": f.get("semantic_name"), "semantic_name": f.get("semantic_name"),
         "dataset": f.get("dataset"), "description": f.get("description", "")}
        for f in catalog_raw
    ]
    slots = [
        {"id": s.id, "type": s.type, "question": s.question, "options_from": s.options_from}
        for s in tree.slots
    ]

    try:
        result = extract_slots(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            hypothesis_text=row["hypothesis_text"],
            slots=slots,
            catalog=catalog,
        )
    except ClaudeScopingError as exc:
        # Not an error the user needs to act on — the questions just get asked.
        logger.info("[%s] Extraction unavailable for %s: %s", request_id, session_id, exc)
        return ExtractResponse(
            session_id=session_id, prefills=[], gaps=[],
            extraction_unavailable=True, detail=str(exc),
        )

    prefills = [
        PrefillOut(
            slot_id=slot_id,
            value=entry.get("value"),
            confidence=entry.get("confidence"),
            evidence_quote=entry.get("evidence_quote"),
            confirmed=False,   # never an answer
        )
        for slot_id, entry in result["slot_prefills"].items()
    ]

    gap_rows = detect_gaps(
        unmatched_concepts=result["unmatched_concepts"],
        catalog=catalog,
        requested_slices=result["requested_slices"],
        filterable_fields=_filterable_fields(),
    )

    # A gap that cannot be written is still reported.  FINDING HC-S6-F8: the
    # failed insert used to be logged and skipped, so "the write failed" and
    # "there are no gaps" reached the caller as the same answer — and the gap
    # record is the whole deliverable of the stop-at-the-wall design.
    persisted = []
    failed_gaps = []
    for gap in gap_rows:
        gap_id = str(uuid.uuid4())
        try:
            sq.insert_gap(
                bq, gap_id=gap_id, session_id=session_id,
                requested_concept=gap["requested_concept"],
                why_unavailable=gap["why_unavailable"],
                nearest_expressible=gap["nearest_expressible"],
                suggested_definition=gap["suggested_definition"],
            )
        except Exception as exc:
            logger.error("[%s] Failed to record capability gap %s for session %s: %s",
                         request_id, gap_id, session_id, exc, exc_info=True)
            failed_gaps.append({**gap, "gap_id": gap_id, "session_id": session_id,
                                "status": "not_recorded"})
        else:
            persisted.append({**gap, "gap_id": gap_id, "session_id": session_id,
                              "status": "open"})

    if persisted:
        logger.info("[%s] Session %s recorded %d capability gap(s)",
                    request_id, session_id, len(persisted))

    detail = None
    if failed_gaps:
        detail = (
            f"{len(failed_gaps)} capability gap(s) could not be written to "
            f"platform.capability_gaps and are returned in gaps_not_recorded. "
            f"They are NOT stored — nothing will surface them later."
        )

    return ExtractResponse(session_id=session_id, prefills=prefills, gaps=persisted,
                           gaps_not_recorded=failed_gaps, detail=detail)


# ── GET /api/v1/scoping/capability-gaps ──────────────────────────────────────


@router.get("/capability-gaps", response_model=CapabilityGapListResponse,
            responses={401: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
            summary="Things the platform could not express")
def list_capability_gaps(
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
    status: str | None = None,
) -> CapabilityGapListResponse:
    """
    Requires the API key.  The gap list is a readable index of what the platform
    cannot yet express — PROJECT-LEAD ruling HC-S6 Q3.
    """
    try:
        rows = sq.list_gaps(bq, status)
    except Exception as exc:
        logger.error("[%s] BigQuery error listing capability gaps: %s", request_id, exc, exc_info=True)
        raise _err(502, "Upstream query failed", "upstream_error", request_id)
    return CapabilityGapListResponse(data=rows)
