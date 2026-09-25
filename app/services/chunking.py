"""Découpage du dialogue selon les limites du provider.

We prefer scene and turn boundaries, then sentences, and only cut brutally as last resort.
A sentence sliced in the middle sounds moche, so we avoid it whenever physically possible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.cast import Cast
from app.models.script import ParsedScript, SegmentKind, StageDirectionMode
from app.providers.base import DialogueChunk, DialogueTurn


SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


class ChunkingError(ValueError):
    pass


@dataclass(slots=True)
class DialogueChunker:
    max_characters: int
    max_unique_voices: int

    def build_chunks(
        self,
        parsed: ParsedScript,
        cast: Cast,
        stage_mode: StageDirectionMode,
        excluded_speakers: set[str] | None = None,
    ) -> list[DialogueChunk]:
        turns = self._build_turns(parsed, cast, stage_mode, excluded_speakers or set())
        chunks: list[DialogueChunk] = []
        current: list[DialogueTurn] = []
        current_chars = 0
        current_voices: set[str] = set()
        current_act: str | None = None
        current_scene: str | None = None
        sequence = 1

        def flush() -> None:
            nonlocal current, current_chars, current_voices, sequence
            if not current:
                return
            chunks.append(
                DialogueChunk(
                    chunk_id=f"chunk_{sequence:05d}",
                    turns=current,
                    act=current_act,
                    scene=current_scene,
                )
            )
            sequence += 1
            current = []
            current_chars = 0
            current_voices = set()

        for turn, act, scene in turns:
            if current and (act != current_act or scene != current_scene):
                flush()
            current_act, current_scene = act, scene

            for split_turn in self._split_turn(turn):
                new_voice_count = len(current_voices | {split_turn.voice_id})
                would_overflow = current_chars + len(split_turn.text) > self.max_characters
                too_many_voices = new_voice_count > self.max_unique_voices
                # Provider says stop, so stop between turns whenever possible. We do not
                # cut dialogue for sport; hard splitting is the emergency sortie only.
                if current and (would_overflow or too_many_voices):
                    flush()
                    current_act, current_scene = act, scene
                current.append(split_turn)
                current_chars += len(split_turn.text)
                current_voices.add(split_turn.voice_id)
        flush()
        self._attach_context(chunks)
        return chunks

    def _build_turns(
        self,
        parsed: ParsedScript,
        cast: Cast,
        stage_mode: StageDirectionMode,
        excluded_speakers: set[str],
    ) -> list[tuple[DialogueTurn, str | None, str | None]]:
        result: list[tuple[DialogueTurn, str | None, str | None]] = []

        def voice_for(speaker: str) -> str:
            assignment = cast.assignments.get(speaker)
            if not assignment or not assignment.voice_id:
                raise ChunkingError(f"No voice is assigned to {speaker}.")
            return assignment.voice_id

        for segment in parsed.segments:
            if segment.kind == SegmentKind.STAGE_DIRECTION:
                if stage_mode != StageDirectionMode.NARRATE:
                    continue
                speaker = "STAGE DIRECTIONS"
                text = segment.text.strip()
                if not text:
                    continue
                result.append(
                    (
                        DialogueTurn(
                            speaker=speaker,
                            voice_id=voice_for(speaker),
                            text=text,
                            source_segment_ids=[segment.segment_id],
                        ),
                        segment.act,
                        segment.scene,
                    )
                )
                continue

            if not segment.speaker or not segment.text.strip() or segment.speaker in excluded_speakers:
                continue

            if stage_mode == StageDirectionMode.NARRATE and segment.stage_direction:
                speaker = "STAGE DIRECTIONS"
                result.append(
                    (
                        DialogueTurn(
                            speaker=speaker,
                            voice_id=voice_for(speaker),
                            text=segment.stage_direction,
                            source_segment_ids=[segment.segment_id],
                        ),
                        segment.act,
                        segment.scene,
                    )
                )

            text = segment.text.strip()
            if stage_mode == StageDirectionMode.PERFORMANCE and segment.stage_direction:
                text = f"[{segment.stage_direction}] {text}".strip()
            result.append(
                (
                    DialogueTurn(
                        speaker=segment.speaker,
                        voice_id=voice_for(segment.speaker),
                        text=text,
                        source_segment_ids=[segment.segment_id],
                    ),
                    segment.act,
                    segment.scene,
                )
            )
        return result

    def _split_turn(self, turn: DialogueTurn) -> list[DialogueTurn]:
        if len(turn.text) <= self.max_characters:
            return [turn]
        pieces = self._split_text(turn.text)
        return [
            DialogueTurn(
                speaker=turn.speaker,
                voice_id=turn.voice_id,
                text=piece,
                source_segment_ids=list(turn.source_segment_ids),
            )
            for piece in pieces
        ]

    def _split_text(self, text: str) -> list[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        units: list[str] = []
        for paragraph in paragraphs or [text.strip()]:
            if len(paragraph) <= self.max_characters:
                units.append(paragraph)
                continue
            sentences = [s.strip() for s in SENTENCE_BOUNDARY_RE.split(paragraph) if s.strip()]
            for sentence in sentences:
                if len(sentence) <= self.max_characters:
                    units.append(sentence)
                else:
                    units.extend(self._hard_split(sentence))

        pieces: list[str] = []
        current = ""
        for unit in units:
            candidate = unit if not current else f"{current} {unit}"
            if len(candidate) <= self.max_characters:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = unit
        if current:
            pieces.append(current)
        return pieces

    def _hard_split(self, text: str) -> list[str]:
        # Last resort. Better an ugly boundary than an invalid API request -- désolé auteur.
        chunks: list[str] = []
        remaining = text.strip()
        while len(remaining) > self.max_characters:
            split_at = remaining.rfind(" ", 0, self.max_characters + 1)
            if split_at < self.max_characters // 2:
                split_at = self.max_characters
            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    @staticmethod
    def _attach_context(chunks: list[DialogueChunk]) -> None:
        for index, chunk in enumerate(chunks):
            if index > 0:
                previous_chunk = chunks[index - 1]
                if previous_chunk.act == chunk.act and previous_chunk.scene == chunk.scene:
                    previous = " ".join(turn.text for turn in previous_chunk.turns)
                    chunk.previous_text = previous[-100:]
            if index + 1 < len(chunks):
                next_chunk = chunks[index + 1]
                if next_chunk.act == chunk.act and next_chunk.scene == chunk.scene:
                    future = " ".join(turn.text for turn in next_chunk.turns)
                    chunk.future_text = future[:100]
