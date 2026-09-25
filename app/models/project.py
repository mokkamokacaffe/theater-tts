"""Etat persistant d'un projet Theater TTS.

This is the little contract between GUI, disk, and generation. Keep secrets out, keep
paths/data explicit, and do not turn project.json into a pseudo-database, merci.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.models.cast import Cast
from app.models.script import ParsedScript, StageDirectionMode


@dataclass(slots=True)
class GenerationSettings:
    model_id: str = "eleven_v3"
    output_format: str = "mp3_44100_128"
    seed: int | None = None
    retries: int = 3
    concurrency: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ProjectState:
    name: str = "Untitled Play"
    root: str = ""
    parsed_script: ParsedScript | None = None
    cast: Cast = field(default_factory=Cast)
    stage_direction_mode: StageDirectionMode = StageDirectionMode.PERFORMANCE
    generation: GenerationSettings = field(default_factory=GenerationSettings)
    manifest: list[dict] = field(default_factory=list)
    speaker_aliases: dict[str, str] = field(default_factory=dict)
    manual_speakers: list[str] = field(default_factory=list)
    excluded_speakers: list[str] = field(default_factory=list)

    @property
    def root_path(self) -> Path:
        return Path(self.root)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "name": self.name,
            "root": self.root,
            "parsed_script": self.parsed_script.to_dict() if self.parsed_script else None,
            "cast": self.cast.to_dict(),
            "stage_direction_mode": self.stage_direction_mode.value,
            "generation": self.generation.to_dict(),
            "manifest": self.manifest,
            "speaker_aliases": self.speaker_aliases,
            "manual_speakers": self.manual_speakers,
            "excluded_speakers": self.excluded_speakers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectState":
        parsed = data.get("parsed_script")
        return cls(
            name=data.get("name", "Untitled Play"),
            root=data.get("root", ""),
            parsed_script=ParsedScript.from_dict(parsed) if parsed else None,
            cast=Cast.from_dict(data.get("cast", {})),
            stage_direction_mode=StageDirectionMode(
                data.get("stage_direction_mode", StageDirectionMode.PERFORMANCE.value)
            ),
            generation=GenerationSettings(**data.get("generation", {})),
            manifest=list(data.get("manifest", [])),
            speaker_aliases=dict(data.get("speaker_aliases", {})),
            manual_speakers=list(data.get("manual_speakers", [])),
            excluded_speakers=list(data.get("excluded_speakers", [])),
        )
