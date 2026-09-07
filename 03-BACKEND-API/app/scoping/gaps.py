"""
Capability-gap detection — deterministic.

ADR-012: when a hypothesis needs something the platform cannot express, the
chat stops and records a gap rather than working around it.  Deciding *whether*
something is genuinely missing is a rule engine, not a judgment call, and it
lives here so it can be tested without a model.

The extractor (Stage 3, app/claude_scoping.py) proposes concepts it could not
map.  This module is the check on that proposal in both directions:

  - it DROPS false gaps — a model claiming "weather is unavailable" is wrong,
    and concepts.json says so without another API call
  - it CLASSIFIES what remains, which matters because the two kinds of gap have
    very different costs to close

The distinction that catches most hypotheses: a concept can exist as a model
FEATURE and still be unusable as a game-universe SLICE.  "X holds when Y" is a
slice question, and GameUniverseFilter currently accepts only div_game and week.
Adding a feature is not a fix for that.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

CONCEPTS_PATH = Path(__file__).parent / "concepts.json"

WHY_FEATURE_CATALOG = "feature_catalog"
WHY_FILTER_SCHEMA = "filter_schema"
WHY_TARGET = "target"

_STOPWORDS = frozenset({
    "the", "a", "an", "of", "in", "on", "for", "with", "and", "or", "to", "is",
    "are", "be", "when", "team", "teams", "game", "games", "better", "worse",
    "more", "less", "perform", "performs", "do", "does", "very", "poor", "good",
})


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in _STOPWORDS}


def load_concepts(path: Path | None = None) -> list[dict[str, Any]]:
    data = json.loads((path or CONCEPTS_PATH).read_text(encoding="utf-8"))
    return data["concepts"]


def catalog_columns(catalog: Iterable[dict[str, Any]]) -> set[str]:
    return {f.get("column") or f.get("semantic_name") or "" for f in catalog}


def resolve_concept(
    concept: str,
    catalog: list[dict[str, Any]],
    concepts: Optional[list[dict[str, Any]]] = None,
) -> Optional[dict[str, Any]]:
    """
    Resolve a plain-English concept to what the platform has.

    Returns {"features": [...], "filterable": bool} when it resolves, else None.
    Alias match first (curated knowledge), then a direct hit on a catalog
    column name or semantic name.
    """
    concepts = load_concepts() if concepts is None else concepts
    toks = _tokens(concept)
    if not toks:
        return None

    for entry in concepts:
        for alias in entry["aliases"]:
            alias_toks = _tokens(alias)
            if alias_toks and alias_toks <= toks:
                return {"features": list(entry["features"]),
                        "filterable": bool(entry["filterable"])}

    for feature in catalog:
        name = (feature.get("column") or feature.get("semantic_name") or "").lower()
        if not name:
            continue
        if _tokens(name) and _tokens(name) <= toks:
            return {"features": [name], "filterable": False}

    return None


def detect_gaps(
    unmatched_concepts: list[str],
    catalog: list[dict[str, Any]],
    requested_slices: Optional[list[str]] = None,
    filterable_fields: Optional[Iterable[str]] = None,
    concepts: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """
    Turn proposed-unmatched concepts and requested slices into capability gaps.

    `unmatched_concepts` — what the extractor could not map to a feature.
    `requested_slices`   — concepts the hypothesis wants to CONDITION on.
    `filterable_fields`  — the fields GameUniverseFilter accepts, read from the
                           schema by the caller so this widens automatically.

    Every returned gap is a dict matching platform.capability_gaps.
    """
    concepts = load_concepts() if concepts is None else concepts
    filterable_fields = set(filterable_fields or ())
    gaps: list[dict[str, Any]] = []
    seen: set[str] = set()

    for concept in unmatched_concepts or []:
        key = concept.strip().lower()
        if not key or key in seen:
            continue
        resolved = resolve_concept(concept, catalog, concepts)
        if resolved is not None:
            # Not a gap. The extractor was wrong; corrected without a model.
            continue
        seen.add(key)
        gaps.append({
            "requested_concept": concept.strip(),
            "why_unavailable": WHY_FEATURE_CATALOG,
            "nearest_expressible": None,
            "suggested_definition": None,
        })

    for slice_concept in requested_slices or []:
        key = f"slice::{slice_concept.strip().lower()}"
        if not slice_concept.strip() or key in seen:
            continue
        resolved = resolve_concept(slice_concept, catalog, concepts)

        if resolved is None:
            # Missing entirely — already covered if it was also reported
            # unmatched; otherwise record it as a feature gap, since you cannot
            # slice on something that does not exist at all.
            if slice_concept.strip().lower() in seen:
                continue
            seen.add(key)
            gaps.append({
                "requested_concept": slice_concept.strip(),
                "why_unavailable": WHY_FEATURE_CATALOG,
                "nearest_expressible": None,
                "suggested_definition": None,
            })
            continue

        already_filterable = resolved["filterable"] or any(
            f in filterable_fields for f in resolved["features"]
        )
        if already_filterable:
            continue

        seen.add(key)
        feats = ", ".join(resolved["features"]) or "no direct feature"
        gaps.append({
            "requested_concept": slice_concept.strip(),
            "why_unavailable": WHY_FILTER_SCHEMA,
            "nearest_expressible": (
                f"Available as model feature(s): {feats}. These can be given to the "
                f"model as inputs, but the game universe cannot currently be "
                f"restricted by them — GameUniverseFilter accepts only "
                f"{', '.join(sorted(filterable_fields)) or 'nothing'}."
            ),
            "suggested_definition": (
                f"Widen GameUniverseFilter.field to accept {feats} from curated.games, "
                f"so '{slice_concept.strip()}' can be asked as a subset rather than "
                f"added as another input column."
            ),
        })

    return gaps
