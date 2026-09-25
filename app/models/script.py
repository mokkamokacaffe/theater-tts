"""Le modèle neutre du script.

Parsers put structure here; providers consume structure from here. Neither side should
know the other's cuisine. This boring middle layer saves much pain later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Iterable


class SegmentKind(StrEnum):
    DIALOGUE = "dialogue"
    STAGE_DIRECTION = "stage_direction"


class StageDirectionMode(StrEnum):
    SKIP = "skip"
    NARRATE = "narrate"
    PERFORMANCE = "performance"


@dataclass(slots=True)
class ScriptSegment:
    segment_id: str
    kind: SegmentKind
    text: str
    speaker: str | None = None
    act: str | None = None
    scene: str | None = None
    stage_direction: str | None = None
    source_line_start: int = 0
    source_line_end: int = 0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptSegment":
        copy = dict(data)
        copy["kind"] = SegmentKind(copy["kind"])
        return cls(**copy)


@dataclass(slots=True)
class ParsedScript:
    source_text: str
    segments: list[ScriptSegment] = field(default_factory=list)
    acts: list[str] = field(default_factory=list)
    scenes: list[str] = field(default_factory=list)

    def speakers(self, stage_mode: StageDirectionMode = StageDirectionMode.SKIP) -> list[str]:
        seen: dict[str, None] = {}
        for segment in self.segments:
            if segment.kind == SegmentKind.DIALOGUE and segment.speaker:
                seen.setdefault(segment.speaker, None)
        if stage_mode == StageDirectionMode.NARRATE and any(
            s.kind == SegmentKind.STAGE_DIRECTION or bool(s.stage_direction) for s in self.segments
        ):
            seen.setdefault("STAGE DIRECTIONS", None)
        return list(seen)

    def dialogue_segments(self) -> Iterable[ScriptSegment]:
        return (s for s in self.segments if s.kind == SegmentKind.DIALOGUE)

    def to_dict(self) -> dict:
        return {
            "source_text": self.source_text,
            "segments": [s.to_dict() for s in self.segments],
            "acts": self.acts,
            "scenes": self.scenes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ParsedScript":
        return cls(
            source_text=data.get("source_text", ""),
            segments=[ScriptSegment.from_dict(s) for s in data.get("segments", [])],
            acts=list(data.get("acts", [])),
            scenes=list(data.get("scenes", [])),
        )
