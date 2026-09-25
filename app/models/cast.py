"""Les données du casting, rien de plus.

A character keeps the same provider voice until the user changes it. These dataclasses
are volontairement boring so project JSON remains lisible even in ten years.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class VoiceInfo:
    voice_id: str
    name: str
    provider: str = "elevenlabs"
    preview_url: str | None = None
    category: str | None = None


@dataclass(slots=True)
class CastAssignment:
    provider: str = "elevenlabs"
    voice_id: str = ""
    voice_name: str = ""


@dataclass(slots=True)
class Cast:
    assignments: dict[str, CastAssignment] = field(default_factory=dict)

    def set_voice(self, speaker: str, voice: VoiceInfo) -> None:
        self.assignments[speaker] = CastAssignment(
            provider=voice.provider,
            voice_id=voice.voice_id,
            voice_name=voice.name,
        )

    def rename_speaker(self, old: str, new: str) -> None:
        if old == new:
            return
        if old in self.assignments:
            self.assignments[new] = self.assignments.pop(old)

    def remove_speaker(self, speaker: str) -> None:
        self.assignments.pop(speaker, None)

    def to_dict(self) -> dict:
        return {speaker: asdict(value) for speaker, value in self.assignments.items()}

    @classmethod
    def from_dict(cls, data: dict) -> "Cast":
        return cls(
            assignments={
                speaker: CastAssignment(**assignment)
                for speaker, assignment in data.items()
            }
        )
