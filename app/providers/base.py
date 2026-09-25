"""Frontière commune pour les moteurs TTS.

The rest of Theater TTS speaks this small vocabulary instead of ElevenLabs dialect. This
is the anti-vendor-lock-in part, mais sans faire une cathédrale d'abstractions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.models.cast import VoiceInfo


class ProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class DialogueTurn:
    speaker: str
    voice_id: str
    text: str
    source_segment_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DialogueChunk:
    chunk_id: str
    turns: list[DialogueTurn]
    act: str | None = None
    scene: str | None = None
    previous_text: str | None = None
    future_text: str | None = None

    @property
    def character_count(self) -> int:
        return sum(len(turn.text) for turn in self.turns)

    @property
    def voice_ids(self) -> set[str]:
        return {turn.voice_id for turn in self.turns}


@dataclass(slots=True)
class GenerationResult:
    path: Path
    request_id: str | None = None
    character_cost: int | None = None


class TTSProvider(ABC):
    name: str
    dialogue_character_limit: int
    dialogue_unique_voice_limit: int

    @abstractmethod
    def get_voices(self) -> list[VoiceInfo]:
        raise NotImplementedError

    @abstractmethod
    def preview_voice(self, voice_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def generate_dialogue(
        self,
        chunk: DialogueChunk,
        destination: Path,
        *,
        model_id: str,
        output_format: str,
        seed: int | None = None,
        retries: int = 3,
    ) -> GenerationResult:
        raise NotImplementedError

    @abstractmethod
    def generate_single_line(
        self,
        turn: DialogueTurn,
        destination: Path,
        *,
        model_id: str,
        output_format: str,
        seed: int | None = None,
        retries: int = 3,
    ) -> GenerationResult:
        raise NotImplementedError
