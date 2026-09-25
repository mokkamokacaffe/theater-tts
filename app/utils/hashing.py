"""Hash stable pour savoir si deux générations sont vraiment identiques.

Canonical JSON goes in, SHA-256 comes out. Deterministic and dull: exactly what a cache key
should be. No clever salt, no horoscope, no surprise.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass


def stable_hash(payload: object) -> str:
    def default(value: object):
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "value"):
            return getattr(value, "value")
        raise TypeError(f"Cannot serialize {type(value)!r}")

    # Sorted keys + compact separators give the same bytes for the same logical payload.
    # Without canonical bytes, deterministic cache is seulement a nice story.
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
