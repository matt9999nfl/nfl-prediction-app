"""
Requirement C — render purity under real data.

Every prior render test used a fixture config with one or two invented
features (tests/test_scoping_core.py uses `fixture_alpha`). These build the
config out of the LIVE feature catalog, at full length, with unicode in the
name and the falsifier — the three things a template function tends to break
on that a two-field fixture never exercises.

Guarantee under test: ADR-012 commitment 3 — the brief cannot drift from the
config, and the hash printed in the brief is the hash dispatch will compare.
"""
from __future__ import annotations

import random

import pytest

pytestmark = pytest.mark.integration

# Deliberately awkward: combining marks, CJK, RTL, an emoji, a backtick that
# could break the markdown the brief is made of, and a newline.
UNICODE_NAME = "Ölïne préssure — 大きい 🏈 `backtick`"
UNICODE_FALSIFIER = "أقل من 50% ATS في كل fold\nsecond line — em dash, naïve café"


def _feature_refs(live_catalog: list[dict]) -> list[dict]:
    """FeatureRef dicts built from the live catalog, not from a fixture."""
    return [
        {
            "dataset": f["dataset"],
            "column": f["semantic_name"],
            "semantic_name": f["semantic_name"],
        }
        for f in live_catalog
    ]


def _answers(tree, features, **overrides):
    answers = {slot.id: slot.default for slot in tree.slots}
    answers.update(
        {
            "features": features,
            "mechanism": "OL pass protection quality is undervalued by the market",
            "falsifier": "below 50% ATS in every fold",
            "name": "live catalog render check",
            "prior_attempts": None,
        }
    )
    answers.update(overrides)
    return answers


@pytest.fixture
def built(scoping_api, live_catalog):
    tree = scoping_api["schema"].load_tree()
    features = _feature_refs(live_catalog)
    return tree, features


def test_render_is_byte_identical_on_the_full_live_catalog(scoping_api, built):
    """A long feature list is where an unstable sort or a set iteration shows up."""
    tree, features = built
    assemble = scoping_api["assemble"].assemble
    record_only = scoping_api["assemble"].record_only_answers
    render = scoping_api["render"].render

    answers = _answers(tree, features)
    payload = assemble(tree, answers)
    briefs = {
        render(
            payload,
            hypothesis_text="Heavier O-lines cover more in poor weather",
            record_only=record_only(tree, answers),
            tree=tree,
        )
        for _ in range(5)
    }
    assert len(briefs) == 1, "render() is not byte-identical across repeat calls"
    assert len(features) >= 20, (
        f"only {len(features)} features in the live catalog — this test is not "
        "exercising a long list any more"
    )


def test_render_is_byte_identical_with_unicode_in_name_and_falsifier(scoping_api, built):
    tree, features = built
    assemble = scoping_api["assemble"].assemble
    record_only = scoping_api["assemble"].record_only_answers
    render = scoping_api["render"].render

    answers = _answers(tree, features, name=UNICODE_NAME, falsifier=UNICODE_FALSIFIER)
    payload = assemble(tree, answers)
    kwargs = dict(
        hypothesis_text="Heavier O-lines cover more — même en hiver",
        record_only=record_only(tree, answers),
        tree=tree,
    )
    first = render(payload, **kwargs)
    assert first == render(payload, **kwargs)
    assert UNICODE_NAME in first, "the experiment name did not survive into the brief"


def test_the_hash_printed_in_the_brief_is_the_hash_dispatch_compares(scoping_api, built):
    """
    The brief tells the reader that approving it approves that exact hash.
    dispatch() recomputes config_hash(assemble(tree, answers)) and compares to
    the approved value, so the printed string and the recomputed one must be
    the same string.
    """
    tree, features = built
    assemble = scoping_api["assemble"].assemble
    record_only = scoping_api["assemble"].record_only_answers
    render = scoping_api["render"].render
    config_hash = scoping_api["hashing"].config_hash

    answers = _answers(tree, features, name=UNICODE_NAME)
    payload = assemble(tree, answers)
    brief = render(
        payload,
        hypothesis_text="unicode in the name must not move the hash",
        record_only=record_only(tree, answers),
        tree=tree,
    )
    expected = config_hash(payload)
    assert f"Config hash: `{expected}`" in brief
    # And the hash dispatch would recompute from the same answers.
    assert config_hash(assemble(tree, answers)) == expected


def test_answer_order_does_not_move_the_hash_or_the_brief(scoping_api, built):
    """
    Slots can be re-answered in any order. Two sessions that reach the same
    answers must reach the same hash, or approval becomes order-dependent.
    """
    tree, features = built
    assemble = scoping_api["assemble"].assemble
    render = scoping_api["render"].render
    record_only = scoping_api["assemble"].record_only_answers
    config_hash = scoping_api["hashing"].config_hash

    answers = _answers(tree, features, name=UNICODE_NAME)
    items = list(answers.items())
    random.Random(20260908).shuffle(items)
    shuffled = dict(items)

    assert config_hash(assemble(tree, answers)) == config_hash(assemble(tree, shuffled))
    kwargs = dict(hypothesis_text="order independence", tree=tree)
    assert render(
        assemble(tree, answers), record_only=record_only(tree, answers), **kwargs
    ) == render(
        assemble(tree, shuffled), record_only=record_only(tree, shuffled), **kwargs
    )


# ── FINDING HC-S6-F2 ─────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING HC-S6-F2: the approved hash covers the config payload only, "
        "not the brief. Changing a record-only answer (mechanism, falsifier, "
        "prior_attempts) rewrites the approved document and leaves the hash "
        "untouched, so two materially different briefs carry the same "
        "approval. Implementation deliberately not modified."
    ),
)
def test_two_different_briefs_cannot_share_one_config_hash(scoping_api, built):
    """
    ADR-012 commitment 3 and the brief's own closing sentence: "If any answer
    changes, the hash changes and approval is required again — the document you
    approve and the config that runs cannot differ."

    That sentence is false for three of the seventeen slots. `falsifier` is one
    of them, and it is the slot the design calls the discipline that separates
    a hypothesis from a fishing trip.
    """
    tree, features = built
    assemble = scoping_api["assemble"].assemble
    record_only = scoping_api["assemble"].record_only_answers
    render = scoping_api["render"].render
    config_hash = scoping_api["hashing"].config_hash

    approved_answers = _answers(
        tree, features, falsifier="below 50% ATS in every fold, no exceptions"
    )
    rewritten_answers = _answers(
        tree, features, falsifier="I will keep this hypothesis whatever happens"
    )

    kwargs = dict(hypothesis_text="record-only drift", tree=tree)
    approved_brief = render(
        assemble(tree, approved_answers),
        record_only=record_only(tree, approved_answers),
        **kwargs,
    )
    rewritten_brief = render(
        assemble(tree, rewritten_answers),
        record_only=record_only(tree, rewritten_answers),
        **kwargs,
    )

    assert approved_brief != rewritten_brief, "fixture is wrong — the briefs must differ"

    approved_hash = config_hash(assemble(tree, approved_answers))
    rewritten_hash = config_hash(assemble(tree, rewritten_answers))
    assert approved_hash != rewritten_hash, (
        "Two different approval documents share one hash. The hash is printed "
        "in the brief as the thing being approved, so approval is bound to less "
        "than the brief claims."
    )
