"""
Canonical hashing of an assembled config.

ADR-012 commitment 3: approval is recorded against the hash of the config, and
dispatch refuses a config whose hash was not approved.  That guarantee is only
as good as the canonicalisation — two configs that mean the same thing must
hash the same, and two that differ must not.

The named failure this module exists to prevent: key ordering or float
formatting making an identical config hash differently between approve and
dispatch, so a legitimate approval is rejected — or worse, a mutated config
slipping through because a difference was normalised away.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    """
    A stable string form of a config.

    - keys sorted, so dict ordering cannot change the hash
    - no insignificant whitespace
    - non-ASCII preserved rather than escaped, so encoding choices don't matter
    - ints and floats keep their own repr: 1 and 1.0 are NOT the same config,
      because `min_sample: 1` and `min_sample: 1.0` would validate differently
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def config_hash(payload: Any) -> str:
    """sha256 of the canonical form, hex-encoded."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
