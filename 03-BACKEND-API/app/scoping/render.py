"""
Config → the brief Matt reads and approves.

ADR-012 commitment 3.  This module is a PURE TEMPLATE FUNCTION.  It must never
import claude_scoping, call a model, hit BigQuery, read a clock, or consult
anything outside its arguments.  render(x) twice must be byte-identical.

The failure being closed: approving a nicely-worded document while a different
config executes.  The brief is not written about the config — it is a
projection of it.  Every fact below is read from the payload; nothing is
narrated, summarised, or inferred.

If you are here to add a generated summary paragraph: that is the contract
violation this file exists to prevent.  Add it to the UI as clearly-labelled
commentary instead, outside the approved artefact.
"""
from __future__ import annotations

from typing import Any

from app.scoping.hashing import config_hash
from app.scoping.schema import ScopingTree

_NOT_SET = "_not set_"


def _fmt(value: Any) -> str:
    if value is None:
        return _NOT_SET
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _features_block(features: list[dict[str, Any]] | None) -> list[str]:
    if not features:
        return ["_none selected_"]
    lines = []
    for f in sorted(features, key=lambda x: (x.get("dataset", ""), x.get("column", ""))):
        label = f.get("semantic_name") or f.get("column", "?")
        lines.append(f"- {label}  (`{f.get('dataset','?')}.{f.get('column','?')}`)")
    lines.append("")
    lines.append(
        f"{len(features)} selected · {len(features) * 2} features in the model "
        f"(each is mirrored home/away)."
    )
    return lines


def _slice_block(game_universe: dict[str, Any] | None) -> list[str]:
    if not game_universe:
        return ["All regular-season games. No slice applied."]
    return [
        f"`{game_universe.get('field')}` {game_universe.get('operator')} "
        f"`{_fmt(game_universe.get('value'))}`",
        "",
        "Only games matching this are trained on and evaluated.",
    ]


def render(
    payload: dict[str, Any],
    *,
    hypothesis_text: str,
    record_only: dict[str, Any],
    tree: ScopingTree,
) -> str:
    """
    Render the approval brief.

    `payload` is the assembled ExperimentCreateRequest dict — the exact object
    that will be hashed, approved, and executed.  The hash is printed in the
    brief so the document and the thing it describes are visibly the same.
    """
    methodology = payload.get("methodology", {}) or {}
    evaluation = payload.get("evaluation", {}) or {}
    model = payload.get("model", {}) or {}

    lines: list[str] = []
    add = lines.append

    add(f"# {payload.get('name', 'Untitled experiment')}")
    add("")
    add("## Hypothesis")
    add("")
    add(hypothesis_text.strip() or _NOT_SET)
    add("")

    # Record-only answers, in the tree's declared order so the brief reads the
    # same way every time regardless of the order they were answered in.
    for slot in tree.record_only_slots:
        if slot.id not in record_only:
            continue
        add(f"## {slot.question}")
        add("")
        add(_fmt(record_only[slot.id]).strip())
        add("")

    add("## What will be predicted")
    add("")
    add(f"Target: `{_fmt(payload.get('target'))}`")
    add("")

    add("## Features")
    add("")
    lines.extend(_features_block(payload.get("features")))
    add("")

    add("## Game universe")
    add("")
    lines.extend(_slice_block(methodology.get("game_universe")))
    add("")

    add("## Methodology")
    add("")
    add(f"- Type: `{_fmt(methodology.get('type'))}`")
    add(f"- Seasons: {_fmt(methodology.get('start_season'))} to {_fmt(methodology.get('end_season'))}")
    add(f"- Training window: {_fmt(methodology.get('train_seasons'))} season(s)")
    add(f"- Held out per fold: {_fmt(methodology.get('test_seasons'))} season(s)")
    add(f"- Model: `{_fmt(model.get('type'))}`")
    hyper = model.get("hyperparams") or {}
    if hyper:
        for k in sorted(hyper):
            add(f"  - `{k}`: {_fmt(hyper[k])}")
    else:
        add("  - default hyperparameters")
    add("")

    add("## How success is judged")
    add("")
    add(f"- Metric: `{_fmt(evaluation.get('metric'))}`")
    add(f"- Success threshold: {_fmt(evaluation.get('success_threshold'))}")
    add(f"- Minimum sample: {_fmt(evaluation.get('min_sample'))} games")
    add("")
    add(
        "This threshold was set before the result was seen. A result above it is "
        "not automatically an edge — against closing lines, an unusually high hit "
        "rate on the full game universe is a leakage suspect until audited."
    )
    add("")

    add("---")
    add("")
    add(f"Config hash: `{config_hash(payload)}`")
    add("")
    add(
        "Approving this brief approves that exact hash. If any answer changes, "
        "the hash changes and approval is required again — the document you "
        "approve and the config that runs cannot differ."
    )

    return "\n".join(lines) + "\n"
