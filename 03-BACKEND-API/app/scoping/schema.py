"""
Models describing the scoping question tree, plus the loader.

The tree is DATA (`scoping_tree.json`), not a prompt.  This module gives that
data a validated shape and provides the introspection the conformance test uses
to prove the tree and `ExperimentCreateRequest` agree.

ADR-012, commitment 2: a question sequence that could produce an invalid config
must fail the build.  `tests/test_scoping_tree.py` is where that is enforced;
everything here exists to make that test possible.

Nothing in this module calls Claude, BigQuery, or any endpoint.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Optional, Union, get_args, get_origin

from pydantic import BaseModel, Field, model_validator

TREE_PATH = Path(__file__).parent / "scoping_tree.json"

# The only three legal forms for `options_from`.  Anything else is a hardcoded
# domain value smuggled into the tree, which is the one thing this file exists
# to prevent.
OPTIONS_SOURCE_FORMS = ("literal:", "endpoint:", "schema:")

SlotType = Literal[
    "text",
    "enum",
    "multi_select",
    "integer",
    "float",
    "filter",
    "object",
]

# Types whose options must come from somewhere declared.
TYPES_REQUIRING_OPTIONS = frozenset({"enum", "multi_select", "filter"})


class Slot(BaseModel):
    """One question in the tree."""

    id: str
    question: str
    type: SlotType
    required: bool

    # Dotted path into ExperimentCreateRequest, e.g. "evaluation.min_sample".
    # None marks a RECORD-ONLY slot: a question worth asking that no config
    # field can hold.  These are stored on the session and rendered into the
    # brief.  They are not decoration — see the tree file's notes.
    binds_to: Optional[str] = None

    options_from: Optional[str] = None
    help: Optional[str] = None
    default: Any = None

    @model_validator(mode="after")
    def _check(self) -> "Slot":
        if self.options_from is not None and not self.options_from.startswith(
            OPTIONS_SOURCE_FORMS
        ):
            raise ValueError(
                f"slot {self.id!r}: options_from must start with one of "
                f"{OPTIONS_SOURCE_FORMS}, got {self.options_from!r}"
            )
        if self.type in TYPES_REQUIRING_OPTIONS and self.options_from is None:
            raise ValueError(
                f"slot {self.id!r}: type {self.type!r} requires options_from"
            )
        if self.binds_to is not None and not re.fullmatch(
            r"[a-z_]+(\.[a-z_]+)*", self.binds_to
        ):
            raise ValueError(
                f"slot {self.id!r}: binds_to must be a dotted lowercase path, "
                f"got {self.binds_to!r}"
            )
        return self

    @property
    def is_record_only(self) -> bool:
        return self.binds_to is None

    def literal_options(self) -> list[str]:
        """The values of a `literal:a,b,c` source.  Empty for other sources."""
        if self.options_from and self.options_from.startswith("literal:"):
            return [v for v in self.options_from[len("literal:") :].split(",") if v]
        return []


class ScopingTree(BaseModel):
    """The whole declared question sequence."""

    version: int
    binds_to_model: str = Field(
        description="Name of the Pydantic model the config slots assemble into."
    )
    slots: list[Slot]

    @model_validator(mode="after")
    def _unique(self) -> "ScopingTree":
        ids = [s.id for s in self.slots]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate slot ids: {sorted(dupes)}")

        bound = [s.binds_to for s in self.slots if s.binds_to]
        dupe_paths = {p for p in bound if bound.count(p) > 1}
        if dupe_paths:
            raise ValueError(f"binds_to path bound by more than one slot: {sorted(dupe_paths)}")
        return self

    @property
    def config_slots(self) -> list[Slot]:
        return [s for s in self.slots if not s.is_record_only]

    @property
    def record_only_slots(self) -> list[Slot]:
        return [s for s in self.slots if s.is_record_only]

    def bound_paths(self) -> set[str]:
        return {s.binds_to for s in self.slots if s.binds_to}

    def by_id(self, slot_id: str) -> Slot:
        for s in self.slots:
            if s.id == slot_id:
                return s
        raise KeyError(slot_id)


def load_tree(path: Path | None = None) -> ScopingTree:
    """Load and validate the tree.  Raises on any malformed slot."""
    p = path or TREE_PATH
    return ScopingTree.model_validate(json.loads(p.read_text(encoding="utf-8")))


# ── Config introspection ─────────────────────────────────────────────────────
#
# Used by the conformance test to walk ExperimentCreateRequest and work out
# which dotted paths a tree must bind.  Stage 2's assembler will reuse this.


def _unwrap_optional(annotation: Any) -> Any:
    """Return T for Optional[T] / T | None; otherwise the annotation itself."""
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _is_nested_model(annotation: Any) -> bool:
    """True for a BaseModel we should recurse into — not for list[Model]."""
    inner = _unwrap_optional(annotation)
    return isinstance(inner, type) and issubclass(inner, BaseModel)


def required_leaf_paths(model: type[BaseModel], _prefix: str = "") -> set[str]:
    """
    Dotted paths of every REQUIRED leaf field of `model`.

    A field is required when it has no default.  Nested BaseModels are walked;
    `list[Model]` is treated as a leaf, because one slot answers the whole list
    (feature selection is a single question, not one question per feature).
    """
    paths: set[str] = set()
    for name, field in model.model_fields.items():
        path = f"{_prefix}{name}"
        if not field.is_required():
            continue
        if _is_nested_model(field.annotation):
            paths |= required_leaf_paths(_unwrap_optional(field.annotation), f"{path}.")
        else:
            paths.add(path)
    return paths


def all_leaf_paths(model: type[BaseModel], _prefix: str = "") -> set[str]:
    """
    Every dotted path a slot may legally bind to.

    Includes leaves AND the paths of nested models, because a slot can answer a
    whole sub-object in one question — `methodology.game_universe` is asked as a
    single filter, not as three separate questions for field/operator/value.
    """
    paths: set[str] = set()
    for name, field in model.model_fields.items():
        path = f"{_prefix}{name}"
        if _is_nested_model(field.annotation):
            paths.add(path)
            paths |= all_leaf_paths(_unwrap_optional(field.annotation), f"{path}.")
        else:
            paths.add(path)
    return paths
