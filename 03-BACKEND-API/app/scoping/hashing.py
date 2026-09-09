"""
Canonical hashing of an assembled config, and of the whole approved brief.

ADR-012 commitment 3: approval is recorded against a hash, and dispatch refuses
anything whose hash was not approved.  That guarantee is only as good as the
canonicalisation — two artefacts that mean the same thing must hash the same,
and two that differ must not.

The named failure this module exists to prevent: key ordering or number
formatting making an identical config hash differently between approve and
dispatch, so a legitimate approval is rejected — or worse, a mutated config
slipping through because a difference was normalised away.

Two functions, two jobs:

  config_hash(payload)                 the ExperimentCreateRequest payload alone.
                                       Printed in the brief, reported as
                                       `config_hash`, and used for staleness.
  approval_hash(payload, record_only)  everything render() consumes — the config
                                       AND the record-only answers (mechanism,
                                       falsifier, prior attempts).  This is what
                                       is stored as `approved_hash` and what
                                       dispatch compares against.

Why two (FINDING HC-S6-F2): the brief renders three record-only slots that no
config field holds.  Hashing the config alone left the falsifier free to change
after approval without moving the hash, so dispatch could proceed against a
document nobody signed off.  The approved artefact and the executed artefact
cannot differ, so the approval hash covers the whole document.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _normalise_numbers(value: Any) -> Any:
    """
    Fold a float with no fractional part to its integer form, recursively.

    FINDING HC-S6-F9.  This module used to state, deliberately, that ints and
    floats were different configs — `min_sample: 1` and `min_sample: 1.0` would
    validate differently, so they were kept apart.

    Storage never honoured that.  BigQuery's JSON type returns `2.0` as `2`, and
    dispatch recomputes the hash from `slot_answers` read back out of BigQuery.
    So any config holding a whole-number float could never match its own
    approval: it failed closed and wedged the session permanently, with
    `approval_mismatch` and no way forward.

    The distinction was unenforceable through the storage layer and was
    therefore never real.  Nothing meaningful is lost by folding it: Pydantic
    already coerces `500.0` to `500` for an int field before anything runs.

    bool is excluded on purpose — it is a subclass of int in Python and must
    keep hashing as `true`/`false`, not as `1`/`0`.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalise_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise_numbers(item) for item in value]
    return value


def canonical_json(payload: Any) -> str:
    """
    A stable string form of a config.

    - keys sorted, so dict ordering cannot change the hash
    - no insignificant whitespace
    - non-ASCII preserved rather than escaped, so encoding choices don't matter
    - whole-number floats folded to ints, so the form survives a storage
      round-trip unchanged (see _normalise_numbers)

    Idempotent across storage: canonical_json(x) == canonical_json(round_trip(x))
    for anything BigQuery's JSON type will hold.
    """
    return json.dumps(
        _normalise_numbers(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def config_hash(payload: Any) -> str:
    """sha256 of the canonical form of the config payload, hex-encoded."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def approval_hash(payload: Any, record_only: Any = None) -> str:
    """
    sha256 over everything the brief renders: the config AND the record-only
    answers.

    The two halves are wrapped in a labelled envelope so that no arrangement of
    config keys can be made to collide with a record-only answer.
    """
    return hashlib.sha256(
        canonical_json({"config": payload, "record_only": record_only or {}}).encode("utf-8")
    ).hexdigest()
