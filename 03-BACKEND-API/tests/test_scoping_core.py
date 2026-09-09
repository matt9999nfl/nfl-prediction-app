"""
Stage 2 tests — Hypothesis Chat deterministic core.

The three guarantees under test, from ADR-012:

  1. render() is pure — the same config renders byte-identically, always.
  2. Canonical hashing — meaning-equal configs hash equal, different ones don't.
  3. Dispatch refuses anything not approved, or approved-then-changed.

Plus the one that makes the stage worth ordering first: the whole flow works
with ANTHROPIC_API_KEY unset and never imports claude_scoping.
"""
from __future__ import annotations

import copy

import pytest

from app.schemas.experiments import ExperimentCreateRequest
from app.scoping import session as sm
from app.scoping.assemble import IncompleteScopingError, assemble, missing_required
from app.scoping.hashing import canonical_json, config_hash
from app.scoping.render import render
from app.scoping.schema import load_tree

CATALOG = [
    {"dataset": "curated", "column": "fixture_alpha", "semantic_name": "Fixture Alpha"},
    {"dataset": "curated", "column": "fixture_beta", "semantic_name": "Fixture Beta"},
]


@pytest.fixture
def tree():
    return load_tree()


def _answer_everything(tree) -> dict:
    answers: dict = {}
    while True:
        q = sm.next_question(tree, answers)
        if q is None:
            return answers
        value = q.default
        if value is None:
            if q.type == "text":
                value = f"answer for {q.slot_id}"
            elif q.type == "multi_select":
                value = CATALOG
        answers = sm.apply_answer(tree, answers, q.slot_id, value)


@pytest.fixture
def complete(tree):
    answers = _answer_everything(tree)
    payload, record_only = sm.build(tree, answers)
    return answers, payload, record_only


# ── the state machine ────────────────────────────────────────────────────────


def test_questions_come_in_tree_order(tree):
    answers: dict = {}
    seen = []
    while True:
        q = sm.next_question(tree, answers)
        if q is None:
            break
        seen.append(q.slot_id)
        answers = sm.apply_answer(tree, answers, q.slot_id, "x")
    assert seen == [s.id for s in tree.slots]


def test_apply_answer_does_not_mutate(tree):
    original: dict = {}
    updated = sm.apply_answer(tree, original, "name", "n")
    assert original == {}
    assert updated == {"name": "n"}


def test_unknown_slot_is_rejected(tree):
    with pytest.raises(sm.SlotNotInTree):
        sm.apply_answer(tree, {}, "not_a_real_slot", "x")


def test_incomplete_answers_cannot_be_assembled(tree):
    """An incomplete config must never reach a hash — hashing makes it approvable."""
    with pytest.raises(IncompleteScopingError):
        assemble(tree, {"name": "only this"})


def test_blank_required_slot_is_reported(tree):
    answers = _answer_everything(tree)
    answers["falsifier"] = None
    assert "falsifier" in missing_required(tree, answers)
    assert not sm.is_complete(tree, answers)


# ── guarantee 1: render is pure ──────────────────────────────────────────────


def test_render_is_byte_identical_across_calls(tree, complete):
    _a, payload, record_only = complete
    first = render(payload, hypothesis_text="h", record_only=record_only, tree=tree)
    for _ in range(5):
        assert render(payload, hypothesis_text="h", record_only=record_only, tree=tree) == first


def test_render_is_insensitive_to_key_order(tree, complete):
    """Same config, different dict ordering — the brief must not change."""
    _a, payload, record_only = complete
    shuffled = {k: payload[k] for k in reversed(list(payload))}
    assert render(shuffled, hypothesis_text="h", record_only=record_only, tree=tree) == \
           render(payload, hypothesis_text="h", record_only=record_only, tree=tree)


def test_render_module_does_not_reach_for_a_model():
    """
    The named contract violation: adding a generated summary to the brief.
    Guarded here rather than left to review.
    """
    import app.scoping.render as r
    source = open(r.__file__, encoding="utf-8").read()
    for forbidden in ("claude_scoping", "anthropic", "Anthropic", "bigquery"):
        assert forbidden not in source.replace("claude_scoping, call a model", ""), \
            f"render.py must not reference {forbidden}"


def test_brief_states_the_hash_it_describes(tree, complete):
    _a, payload, record_only = complete
    brief = render(payload, hypothesis_text="h", record_only=record_only, tree=tree)
    assert config_hash(payload) in brief


def test_brief_carries_the_record_only_answers(tree, complete):
    """The falsifier is the reason record-only slots exist. It must reach the page."""
    _a, payload, record_only = complete
    brief = render(payload, hypothesis_text="h", record_only=record_only, tree=tree)
    assert record_only["falsifier"] in brief
    assert record_only["mechanism"] in brief


# ── guarantee 2: canonical hashing ───────────────────────────────────────────


def test_key_order_does_not_change_the_hash(complete):
    _a, payload, _ro = complete
    shuffled = {k: payload[k] for k in reversed(list(payload))}
    assert config_hash(shuffled) == config_hash(payload)


def test_nested_key_order_does_not_change_the_hash(complete):
    _a, payload, _ro = complete
    other = copy.deepcopy(payload)
    other["methodology"] = {k: other["methodology"][k]
                            for k in reversed(list(other["methodology"]))}
    assert config_hash(other) == config_hash(payload)


def test_a_changed_value_changes_the_hash(complete):
    _a, payload, _ro = complete
    other = copy.deepcopy(payload)
    other["evaluation"]["min_sample"] += 1
    assert config_hash(other) != config_hash(payload)


def test_a_whole_number_float_hashes_as_its_integer_form(complete):
    """
    REPLACES test_int_and_float_are_not_the_same_config.

    That test asserted `min_sample: 500` and `500.0` were different configs,
    which is what hashing.py used to claim. FINDING HC-S6-F9: storage never
    honoured the distinction. BigQuery's JSON type returns 2.0 as 2, and
    dispatch recomputes the hash from answers read back out of BigQuery — so a
    config holding a whole-number float could never match its own approval and
    the session wedged permanently with `approval_mismatch`.

    The distinction was unenforceable through the storage layer, so it is gone.
    Pydantic coerces 500.0 to 500 for an int field before anything runs, so the
    two really are the same experiment.
    """
    _a, payload, _ro = complete
    other = copy.deepcopy(payload)
    other["evaluation"]["min_sample"] = float(other["evaluation"]["min_sample"])
    assert config_hash(other) == config_hash(payload)


def test_a_real_fractional_difference_still_moves_the_hash(complete):
    """The fold is only of the .0 case — 500 and 500.5 are different designs."""
    _a, payload, _ro = complete
    other = copy.deepcopy(payload)
    other["evaluation"]["min_sample"] = other["evaluation"]["min_sample"] + 0.5
    assert config_hash(other) != config_hash(payload)


def test_booleans_do_not_collapse_into_numbers(complete):
    """bool is an int subclass in Python; `true` must not canonicalise as `1`."""
    from app.scoping.hashing import canonical_json
    assert canonical_json({"x": True}) == '{"x":true}'
    assert config_hash({"x": True}) != config_hash({"x": 1})


def test_canonical_json_is_stable_and_sorted(complete):
    _a, payload, _ro = complete
    assert canonical_json(payload) == canonical_json(payload)
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_hash_is_sha256_hex(complete):
    _a, payload, _ro = complete
    h = config_hash(payload)
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


# ── the assembled config ─────────────────────────────────────────────────────


def test_assembled_payload_validates(complete):
    _a, payload, _ro = complete
    ExperimentCreateRequest.model_validate(payload)


def test_record_only_answers_never_enter_the_config(tree, complete):
    _a, payload, record_only = complete
    assert set(record_only) == {"mechanism", "falsifier", "prior_attempts"} - {
        s.id for s in tree.record_only_slots if s.id not in record_only
    }
    flat = canonical_json(payload)
    for value in record_only.values():
        assert str(value) not in flat, "a record-only answer leaked into the config"


def test_optional_slot_left_blank_is_omitted_not_nulled(tree):
    """
    game_universe left blank must be absent, so Pydantic applies its own default.
    Writing an explicit null is how optional fields start failing validation.
    """
    answers = _answer_everything(tree)
    answers["game_universe"] = None
    payload = assemble(tree, answers)
    assert "game_universe" not in payload["methodology"]
    ExperimentCreateRequest.model_validate(payload)


# ── guarantee 3: nothing runs unapproved ─────────────────────────────────────
#
# Endpoint-level enforcement lives in test_scoping_api.py; these cover the
# comparison itself, which is what those endpoints depend on.


def test_changing_an_answer_invalidates_a_prior_approval(tree, complete):
    answers, payload, _ro = complete
    approved = config_hash(payload)

    answers = sm.apply_answer(tree, answers, "min_sample", payload["evaluation"]["min_sample"] + 1)
    new_payload, _ = sm.build(tree, answers)

    assert config_hash(new_payload) != approved


def test_stage_2_needs_no_anthropic_key(monkeypatch, tree):
    """
    The ordering claim in the build plan: the deterministic core is a complete
    feature with no model in the loop. If this fails, the 60/30/10 split is wrong.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    answers = _answer_everything(tree)
    payload, record_only = sm.build(tree, answers)
    brief = render(payload, hypothesis_text="h", record_only=record_only, tree=tree)
    assert config_hash(payload) in brief
    ExperimentCreateRequest.model_validate(payload)
