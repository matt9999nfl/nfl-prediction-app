"""
Hypothesis Chat — scoping package.

Stage 0 (this stage) contains only the declared question tree and the models
that describe it.  No endpoints, no BigQuery, no Claude calls.

See ../../00-PROJECT-LEAD/HYPOTHESIS-CHAT-BUILD-PLAN.md and
../../docs/DECISIONS.md ADR-012.
"""
from app.scoping.schema import (
    OPTIONS_SOURCE_FORMS,
    ScopingTree,
    Slot,
    load_tree,
    required_leaf_paths,
)

__all__ = [
    "OPTIONS_SOURCE_FORMS",
    "ScopingTree",
    "Slot",
    "load_tree",
    "required_leaf_paths",
]
