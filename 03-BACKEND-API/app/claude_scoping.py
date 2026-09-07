"""
Claude API integration for the Hypothesis Chat.

Second integration point in this codebase; `claude_inference.py` (ADR-007) is
the first, and this deliberately mirrors its shape — one module, lazy import,
fixed output keys validated before return, a dedicated error class the caller
converts to 503.

Stage 3 public function:
  extract_slots(api_key, model, hypothesis_text, slots, catalog) → dict

Returned dict has exactly these three keys:
  slot_prefills        {slot_id: {value, confidence, evidence_quote}}
  unmatched_concepts   [str]  — things it could not map to a feature
  requested_slices     [str]  — things the hypothesis wants to CONDITION on

What this function is NOT allowed to produce, enforced below rather than asked
for in the prompt (ADR-012):
  - a slot id the tree does not declare
  - a feature that is not in the live catalog
  - any key beyond the three above

And what it cannot do at all: its output is a set of PRE-FILLS. A pre-fill is
never an answer. The caller shows the question populated and unconfirmed; only
an explicit answer call commits it. See app/routers/scoping.py.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_KEYS = frozenset({"slot_prefills", "unmatched_concepts", "requested_slices"})

MAX_HYPOTHESIS_CHARS = 2000


class ClaudeScopingError(Exception):
    """Raised when the Claude API call or response parsing/validation fails."""


def _build_prompt(
    hypothesis_text: str,
    slots: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> str:
    slot_lines = [
        f"- {s['id']} ({s['type']}"
        + (f", options: {s['options_from']}" if s.get("options_from") else "")
        + f"): {s['question']}"
        for s in slots
    ]
    feature_lines = [
        f"- {f.get('column') or f.get('semantic_name')}: {f.get('description','')}"
        for f in catalog
    ]
    return f"""A user of an NFL prediction platform has stated a hypothesis. Map it onto the platform's experiment configuration where you can, and say plainly what you could not map.

HYPOTHESIS:
{hypothesis_text[:MAX_HYPOTHESIS_CHARS]}

SLOTS you may fill (use these ids exactly; omit any you cannot fill from the hypothesis):
{chr(10).join(slot_lines)}

FEATURE CATALOG (the ONLY features that exist; never invent one):
{chr(10).join(feature_lines)}

Return JSON with exactly these keys:
- slot_prefills: {{slot_id: {{"value": <value>, "confidence": <0..1>, "evidence_quote": "<the words in the hypothesis that led you here>"}}}}
- unmatched_concepts: [strings] — concepts the hypothesis depends on that map to NO feature in the catalog above
- requested_slices: [strings] — concepts the hypothesis wants to CONDITION on, i.e. "X holds WHEN Y". Put Y here. Include it even if it is also a feature.

Rules:
- Only fill a slot when the hypothesis actually says something about it. Do not guess to be helpful; an omitted slot is asked as a normal question.
- Never invent a feature. If the hypothesis needs a measurement not in the catalog, put it in unmatched_concepts.
- evidence_quote must be words from the hypothesis, not your paraphrase.

Return only the JSON object — no markdown, no explanation."""


def _strip_code_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", r"\1", text.strip(), flags=re.DOTALL).strip()


def _validate(parsed: dict, valid_slot_ids: set[str], valid_features: set[str]) -> dict:
    """
    Reject anything outside the contract.

    A response that fails here raises rather than being repaired — a silently
    corrected model response is how a wrong pre-fill reaches the user looking
    like a confident one.
    """
    missing = REQUIRED_KEYS - parsed.keys()
    if missing:
        raise ClaudeScopingError(f"response missing required keys: {sorted(missing)}")
    extra = parsed.keys() - REQUIRED_KEYS
    if extra:
        raise ClaudeScopingError(f"response has unexpected keys: {sorted(extra)}")

    prefills = parsed["slot_prefills"]
    if not isinstance(prefills, dict):
        raise ClaudeScopingError("slot_prefills must be an object")

    unknown = set(prefills) - valid_slot_ids
    if unknown:
        raise ClaudeScopingError(f"response references slot(s) not in the tree: {sorted(unknown)}")

    for slot_id, entry in prefills.items():
        if not isinstance(entry, dict) or "value" not in entry:
            raise ClaudeScopingError(f"slot_prefills[{slot_id}] must be an object with a 'value'")

    # Features are the one place a hallucination would be materially harmful:
    # it would look like a real selection. Checked against the live catalog.
    feature_entry = prefills.get("features")
    if feature_entry is not None:
        value = feature_entry.get("value")
        if not isinstance(value, list):
            raise ClaudeScopingError("slot_prefills.features.value must be a list")
        for ref in value:
            column = (ref or {}).get("column") if isinstance(ref, dict) else None
            if column not in valid_features:
                raise ClaudeScopingError(
                    f"response proposed a feature that is not in the catalog: {column!r}"
                )

    for key in ("unmatched_concepts", "requested_slices"):
        if not isinstance(parsed[key], list) or not all(isinstance(x, str) for x in parsed[key]):
            raise ClaudeScopingError(f"{key} must be a list of strings")

    return parsed


def extract_slots(
    api_key: str,
    model: str,
    hypothesis_text: str,
    slots: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> dict:
    """
    Map a plain-English hypothesis onto slot pre-fills.

    Raises ClaudeScopingError on any API failure, parse error, or contract
    violation. Callers convert this to 503 / ai_unavailable and fall back to
    asking every question normally — the session must still complete without it.
    """
    if not api_key:
        raise ClaudeScopingError("ANTHROPIC_API_KEY is not configured")

    try:
        import anthropic  # noqa: PLC0415 — lazy import keeps startup fast
    except ImportError as exc:
        raise ClaudeScopingError("anthropic package not installed") from exc

    prompt = _build_prompt(hypothesis_text, slots, catalog)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("Claude scoping call failed: %s", exc)
        raise ClaudeScopingError(f"Claude API call failed: {exc}") from exc

    try:
        raw_text = message.content[0].text
    except (IndexError, AttributeError) as exc:
        raise ClaudeScopingError(f"Unexpected Claude response shape: {exc}") from exc

    try:
        parsed = json.loads(_strip_code_fences(raw_text))
    except json.JSONDecodeError as exc:
        logger.warning("Claude scoping returned non-JSON: %s…", raw_text[:200])
        raise ClaudeScopingError(f"response is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ClaudeScopingError(f"response is not a JSON object (got {type(parsed).__name__})")

    valid_slot_ids = {s["id"] for s in slots}
    valid_features = {(f.get("column") or f.get("semantic_name")) for f in catalog}
    return _validate(parsed, valid_slot_ids, valid_features)
