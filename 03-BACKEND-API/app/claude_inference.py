"""
Claude API integration for AI-assisted dataset schema inference.

Single public function:
  infer_dataset_schema(api_key, model, column_names, sample_rows) → dict

The returned dict has exactly these five keys (validated before return):
  suggested_join_key_type      str
  suggested_join_key_columns   dict[str, str]
  suggested_columns            list[dict]
  data_quality_flags           list[dict]
  confidence                   float

Any failure — API error, network timeout, malformed JSON, missing keys —
raises ClaudeInferenceError.  Callers convert this to 503 / ai_unavailable.

Prompt design follows BACKEND_API_SPEC_PHASE2.md § Step 5 exactly.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

REQUIRED_KEYS = frozenset(
    {
        "suggested_join_key_type",
        "suggested_join_key_columns",
        "suggested_columns",
        "data_quality_flags",
        "confidence",
    }
)


class ClaudeInferenceError(Exception):
    """Raised when the Claude API call or response parsing fails."""


def _build_prompt(column_names: list[str], sample_rows: list[dict]) -> str:
    """
    Build the inference prompt per BACKEND_API_SPEC_PHASE2.md § Step 5.
    sample_rows may be empty if the user_datasets table has no rows yet.
    """
    return f"""You are analyzing an NFL dataset uploaded by a user.
Column names: {json.dumps(column_names)}
Sample rows (first 5): {json.dumps(sample_rows, default=str)}

Return JSON with:
- suggested_join_key_type: "game_id" | "player_season_week" | "team_season_week"
- suggested_join_key_columns: {{role: column_name}} mapping
- suggested_columns: [{{"column_name": str, "semantic_name": str, "description": str, "data_type": str}}]
- data_quality_flags: [{{"column": str, "issue": str, "severity": "warning"|"error"}}]
- confidence: float 0..1

Return only the JSON object — no markdown, no explanation."""


def _strip_code_fences(text: str) -> str:
    """
    Remove optional markdown code fences (```json ... ``` or ``` ... ```)
    that Claude sometimes wraps around JSON responses.
    """
    # Match ```[lang]\n...\n``` or ```...\n```
    stripped = re.sub(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", r"\1", text.strip(), flags=re.DOTALL)
    return stripped.strip()


def _validate_response(parsed: dict) -> None:
    """Raise ClaudeInferenceError if any of the five required keys are absent."""
    missing = REQUIRED_KEYS - parsed.keys()
    if missing:
        raise ClaudeInferenceError(
            f"Claude response missing required keys: {sorted(missing)}"
        )


def infer_dataset_schema(
    api_key: str,
    model: str,
    column_names: list[str],
    sample_rows: list[dict],
) -> dict:
    """
    Call Claude to infer schema mapping suggestions for a user-uploaded dataset.

    Parameters
    ----------
    api_key:       Anthropic API key (from settings.anthropic_api_key).
    model:         Model ID (from settings.anthropic_model).
    column_names:  All column names in the uploaded dataset.
    sample_rows:   First N rows as a list of dicts (N is typically 5).

    Returns
    -------
    A dict with the five required keys (see module docstring).

    Raises
    ------
    ClaudeInferenceError — on any API failure, network error, parse error,
                           or missing keys in Claude's response.
    """
    try:
        import anthropic  # noqa: PLC0415 — lazy import keeps startup fast
    except ImportError as exc:
        raise ClaudeInferenceError("anthropic package not installed") from exc

    prompt = _build_prompt(column_names, sample_rows)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("Claude API call failed: %s", exc)
        raise ClaudeInferenceError(f"Claude API call failed: {exc}") from exc

    # Extract text content from the first content block.
    try:
        raw_text = message.content[0].text
    except (IndexError, AttributeError) as exc:
        raise ClaudeInferenceError(f"Unexpected Claude response shape: {exc}") from exc

    # Parse JSON, tolerating optional code fences.
    cleaned = _strip_code_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Claude returned non-JSON response: %s…", raw_text[:200])
        raise ClaudeInferenceError(f"Claude response is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ClaudeInferenceError(
            f"Claude response is not a JSON object (got {type(parsed).__name__})"
        )

    _validate_response(parsed)
    return parsed
