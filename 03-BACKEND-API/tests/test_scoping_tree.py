"""
Stage 0 conformance tests — Hypothesis Chat.

These are not formalities.  ADR-012 commitment 2 says a question sequence that
could produce an invalid config must fail the build.  This file is where that
is enforced, in both directions:

  tree -> config : filling every slot produces a valid ExperimentCreateRequest
  config -> tree : every required field of ExperimentCreateRequest has a slot

If either direction is unenforced, the tree can drift from the platform and the
chat will confidently ask the wrong questions.

No network, no BigQuery, no Claude.  The feature catalog is a fixture.
"""
from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from app.schemas.experiments import ExperimentCreateRequest, GameUniverseFilter
from app.scoping.schema import (
    OPTIONS_SOURCE_FORMS,
    ScopingTree,
    load_tree,
    required_leaf_paths,
)

# A stand-in for GET /api/v1/features.  Deliberately fake names: if any of these
# leak into scoping_tree.json, test_no_hardcoded_feature_names catches it.
FIXTURE_CATALOG = [
    {"feature_id": "curated.fixture_alpha", "dataset": "curated", "column": "fixture_alpha",
     "semantic_name": "Fixture Alpha"},
    {"feature_id": "curated.fixture_beta", "dataset": "curated", "column": "fixture_beta",
     "semantic_name": "Fixture Beta"},
]


@pytest.fixture
def tree() -> ScopingTree:
    return load_tree()


# ── direction 1: config -> tree ──────────────────────────────────────────────


def test_every_required_config_field_is_bound(tree: ScopingTree) -> None:
    """Every required field of ExperimentCreateRequest has exactly one slot."""
    required = required_leaf_paths(ExperimentCreateRequest)
    bound = tree.bound_paths()
    missing = required - bound
    assert not missing, (
        f"{len(missing)} required config field(s) have no slot and would never be "
        f"asked about: {sorted(missing)}"
    )


def test_no_config_field_is_bound_twice(tree: ScopingTree) -> None:
    """Two slots writing the same path means one silently overwrites the other."""
    bound = [s.binds_to for s in tree.slots if s.binds_to]
    dupes = sorted({p for p in bound if bound.count(p) > 1})
    assert not dupes, f"path(s) bound by more than one slot: {dupes}"


def test_no_slot_binds_to_a_nonexistent_field(tree: ScopingTree) -> None:
    """A typo'd binds_to path would silently never reach the config."""
    from app.scoping.schema import all_leaf_paths

    valid = all_leaf_paths(ExperimentCreateRequest)
    unknown = sorted(tree.bound_paths() - valid)
    assert not unknown, (
        f"slot(s) bind to path(s) that do not exist on ExperimentCreateRequest: {unknown}"
    )


# ── direction 2: tree -> config ──────────────────────────────────────────────


def _sample_value(slot, catalog):
    """A value of the declared type for one slot."""
    if slot.type == "enum":
        return slot.literal_options()[0]
    if slot.type == "multi_select":
        return [{"dataset": f["dataset"], "column": f["column"],
                 "semantic_name": f["semantic_name"]} for f in catalog]
    if slot.type == "integer":
        return slot.default if isinstance(slot.default, int) else 1
    if slot.type == "float":
        return slot.default if isinstance(slot.default, (int, float)) else 0.5
    if slot.type == "filter":
        return GameUniverseFilter(field="div_game", operator="eq", value=True).model_dump()
    if slot.type == "object":
        return {}
    return "sample text"


def _assemble(tree: ScopingTree, catalog) -> dict:
    """Fill every config slot with a declared-type value and nest by binds_to."""
    out: dict = {}
    for slot in tree.config_slots:
        parts = slot.binds_to.split(".")
        cursor = out
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = _sample_value(slot, catalog)
    return out


def test_filled_tree_produces_a_valid_request(tree: ScopingTree) -> None:
    """The whole point: answering every question yields something that validates."""
    ExperimentCreateRequest.model_validate(_assemble(tree, FIXTURE_CATALOG))


def test_filled_tree_without_optional_slots_still_validates(tree: ScopingTree) -> None:
    """Optional slots must genuinely be optional — skipping them can't break assembly."""
    payload: dict = {}
    for slot in tree.config_slots:
        if not slot.required:
            continue
        parts = slot.binds_to.split(".")
        cursor = payload
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = _sample_value(slot, FIXTURE_CATALOG)
    ExperimentCreateRequest.model_validate(payload)


def test_removing_a_bound_slot_is_caught(tree: ScopingTree) -> None:
    """
    The test must BITE.  Drop a required slot and the coverage check has to fail;
    if this passes silently, every other assertion here is decorative.
    """
    required = required_leaf_paths(ExperimentCreateRequest)
    victim = next(s for s in tree.config_slots if s.binds_to in required)

    mutilated = ScopingTree(
        version=tree.version,
        binds_to_model=tree.binds_to_model,
        slots=[s for s in tree.slots if s.id != victim.id],
    )
    assert required - mutilated.bound_paths() == {victim.binds_to}


# ── the properties that keep the tree from drifting ──────────────────────────


def test_no_hardcoded_feature_names() -> None:
    """
    Feature options resolve from the live catalog at ask-time.  A feature name
    written into the tree is a second source of truth that will go stale.
    """
    raw = (load_tree.__globals__["TREE_PATH"]).read_text(encoding="utf-8")
    leaked = [f["feature_id"] for f in FIXTURE_CATALOG if f["feature_id"] in raw]
    assert not leaked, f"feature id(s) hardcoded in the tree: {leaked}"

    tree = load_tree()
    feature_slots = [s for s in tree.config_slots if s.binds_to == "features"]
    assert feature_slots, "no slot binds to `features`"
    for s in feature_slots:
        assert s.options_from.startswith("endpoint:"), (
            f"slot {s.id!r} must resolve features from the live catalog, "
            f"got {s.options_from!r}"
        )


def test_filter_options_derive_from_the_schema(tree: ScopingTree) -> None:
    """
    When GameUniverseFilter is widened to accept more of curated.games, the tree
    must widen with it and require no edit.  That only holds if the slot points
    at the schema rather than listing fields.
    """
    slots = [s for s in tree.slots if s.type == "filter"]
    assert slots, "no filter slot — the game-universe slice would be unaskable"
    for s in slots:
        assert s.options_from == "schema:GameUniverseFilter", (
            f"slot {s.id!r} must derive options from the schema, got {s.options_from!r}"
        )
    allowed = set(GameUniverseFilter.model_fields["field"].annotation.__args__)
    raw = (load_tree.__globals__["TREE_PATH"]).read_text(encoding="utf-8")
    for field_name in allowed:
        assert f'"{field_name}"' not in raw, (
            f"filter field {field_name!r} is hardcoded in the tree; it must come "
            f"from GameUniverseFilter so the tree widens automatically"
        )


def test_options_from_uses_only_the_three_declared_forms(tree: ScopingTree) -> None:
    for s in tree.slots:
        if s.options_from is not None:
            assert s.options_from.startswith(OPTIONS_SOURCE_FORMS), (
                f"slot {s.id!r}: {s.options_from!r}"
            )


def test_enum_literals_match_the_config_schema(tree: ScopingTree) -> None:
    """
    A literal: list that drifts from the Pydantic Literal is how the tree starts
    offering options the API rejects.
    """
    for slot in tree.config_slots:
        opts = slot.literal_options()
        if not opts:
            continue
        model, _, field = slot.binds_to.rpartition(".")
        target = ExperimentCreateRequest
        for part in [p for p in model.split(".") if p]:
            target = target.model_fields[part].annotation
        annotation = target.model_fields[field].annotation
        args = getattr(annotation, "__args__", None)
        if args:
            assert set(opts) <= set(args), (
                f"slot {slot.id!r} offers {sorted(set(opts) - set(args))} which "
                f"{slot.binds_to} does not accept"
            )


# ── record-only slots ────────────────────────────────────────────────────────


def test_record_only_slots_exist(tree: ScopingTree) -> None:
    assert len(tree.record_only_slots) >= 2


def test_a_falsifier_is_asked_and_is_required(tree: ScopingTree) -> None:
    """
    Without this the feature is a config builder.  With it, it's an experiment
    that can teach you something.
    """
    falsifier = tree.by_id("falsifier")
    assert falsifier.is_record_only
    assert falsifier.required


def test_prior_attempts_is_asked(tree: ScopingTree) -> None:
    """Stage 4's multiple-comparisons check has no input without this."""
    assert tree.by_id("prior_attempts").is_record_only


# ── tree file hygiene ────────────────────────────────────────────────────────


def test_tree_binds_to_the_strict_request_model(tree: ScopingTree) -> None:
    """
    Not ExperimentConfig: its `target` was loosened to plain str for legacy BQ
    rows, so binding there would let the tree emit an invalid target and pass.
    """
    assert tree.binds_to_model == "ExperimentCreateRequest"


def test_duplicate_slot_ids_are_rejected(tree: ScopingTree) -> None:
    raw = json.loads((load_tree.__globals__["TREE_PATH"]).read_text(encoding="utf-8"))
    dup = copy.deepcopy(raw)
    dup["slots"].append(copy.deepcopy(dup["slots"][0]))
    with pytest.raises(ValidationError):
        ScopingTree.model_validate(dup)


def test_every_slot_has_a_question(tree: ScopingTree) -> None:
    for s in tree.slots:
        assert s.question.strip(), f"slot {s.id!r} has no question text"
