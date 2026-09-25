"""Orchestrateur de génération: plan, cache, provider, manifest.

This service decides what must cost an API call and what can be reused. The rule is simple:
unchanged inputs do not spend credits twice. L'argent n'est pas un type de cache.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from app.models.project import ProjectState
from app.project.cache import CacheStore
from app.providers.base import DialogueChunk, TTSProvider
from app.services.chunking import DialogueChunker
from app.utils.hashing import stable_hash


@dataclass(slots=True)
class GenerationPlan:
    chunks: list[DialogueChunk]
    total_characters: int
    cached_chunks: int
    api_chunks: int


class GenerationService:
    def __init__(self, provider: TTSProvider):
        self.provider = provider

    def plan(self, project: ProjectState) -> GenerationPlan:
        if not project.parsed_script:
            raise ValueError("Parse a script before generating audio.")
        chunker = DialogueChunker(
            max_characters=self.provider.dialogue_character_limit,
            max_unique_voices=self.provider.dialogue_unique_voice_limit,
        )
        chunks = chunker.build_chunks(
            project.parsed_script,
            project.cast,
            project.stage_direction_mode,
            excluded_speakers=set(project.excluded_speakers),
        )
        cache = CacheStore(project.root_path / "cache")
        cached = 0
        for chunk in chunks:
            key = self.chunk_hash(project, chunk)
            if cache.get(key):
                cached += 1
        return GenerationPlan(
            chunks=chunks,
            total_characters=sum(c.character_count for c in chunks),
            cached_chunks=cached,
            api_chunks=len(chunks) - cached,
        )

    def generate(
        self,
        project: ProjectState,
        plan: GenerationPlan | None = None,
        *,
        cancel_event: Event | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> list[dict]:
        plan = plan or self.plan(project)
        cache = CacheStore(project.root_path / "cache")
        records: list[dict] = []
        total = len(plan.chunks)

        for index, chunk in enumerate(plan.chunks, start=1):
            if cancel_event and cancel_event.is_set():
                break
            if progress:
                progress(index - 1, total, f"Preparing {chunk.chunk_id}")

            key = self.chunk_hash(project, chunk)
            extension = self._extension_for(project.generation.output_format)
            destination = self._chunk_destination(project, chunk, extension)
            destination.parent.mkdir(parents=True, exist_ok=True)
            cached_path = cache.get(key)
            request_id = None
            character_cost = None
            from_cache = cached_path is not None

            # Cache hit = zero paid request. This branch is deliberately boring and precious.
            if cached_path is not None:
                if cached_path.resolve() != destination.resolve():
                    shutil.copy2(cached_path, destination)
            else:
                if progress:
                    progress(index - 1, total, f"Generating {chunk.chunk_id}")
                result = self.provider.generate_dialogue(
                    chunk,
                    destination,
                    model_id=project.generation.model_id,
                    output_format=project.generation.output_format,
                    seed=project.generation.seed,
                    retries=project.generation.retries,
                )
                request_id = result.request_id
                character_cost = result.character_cost
                cache.put(key, destination)

            record = {
                "segment_id": chunk.chunk_id,
                "type": "dialogue_chunk",
                "act": chunk.act,
                "scene": chunk.scene,
                "speakers": [turn.speaker for turn in chunk.turns],
                "source_segment_ids": [
                    segment_id for turn in chunk.turns for segment_id in turn.source_segment_ids
                ],
                "text": "\n".join(f"{turn.speaker}: {turn.text}" for turn in chunk.turns),
                "voice_ids": [turn.voice_id for turn in chunk.turns],
                "audio_file": str(destination.relative_to(project.root_path)),
                "hash": key,
                "status": "complete",
                "request_id": request_id,
                "character_cost": character_cost,
                "cached": from_cache,
            }
            self._upsert_manifest(project, record)
            records.append(record)
            if progress:
                progress(index, total, f"Completed {chunk.chunk_id}")
        return records

    def regenerate_chunk(
        self,
        project: ProjectState,
        chunk_id: str,
        *,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        plan = self.plan(project)
        chunk = next((c for c in plan.chunks if c.chunk_id == chunk_id), None)
        if chunk is None:
            raise ValueError(f"Unknown chunk: {chunk_id}")
        extension = self._extension_for(project.generation.output_format)
        destination = self._chunk_destination(project, chunk, extension)
        result = self.provider.generate_dialogue(
            chunk,
            destination,
            model_id=project.generation.model_id,
            output_format=project.generation.output_format,
            seed=project.generation.seed,
            retries=project.generation.retries,
        )
        key = self.chunk_hash(project, chunk)
        CacheStore(project.root_path / "cache").put(key, destination)
        record = {
            "segment_id": chunk.chunk_id,
            "type": "dialogue_chunk",
            "act": chunk.act,
            "scene": chunk.scene,
            "speakers": [turn.speaker for turn in chunk.turns],
            "source_segment_ids": [s for t in chunk.turns for s in t.source_segment_ids],
            "text": "\n".join(f"{t.speaker}: {t.text}" for t in chunk.turns),
            "voice_ids": [t.voice_id for t in chunk.turns],
            "audio_file": str(destination.relative_to(project.root_path)),
            "hash": key,
            "status": "complete",
            "request_id": result.request_id,
            "character_cost": result.character_cost,
            "cached": False,
        }
        self._upsert_manifest(project, record)
        if progress:
            progress(1, 1, f"Regenerated {chunk.chunk_id}")
        return record

    def chunk_hash(self, project: ProjectState, chunk: DialogueChunk) -> str:
        # Every input capable of changing the sound must participate. Forget one and the cache
        # becomes a liar; add irrelevant things and we waste credits. Voilà the balance.
        return stable_hash(
            {
                "provider": self.provider.name,
                "model_id": project.generation.model_id,
                "output_format": project.generation.output_format,
                "seed": project.generation.seed,
                "stage_direction_mode": project.stage_direction_mode.value,
                "previous_text": chunk.previous_text,
                "future_text": chunk.future_text,
                "turns": [
                    {
                        "speaker": t.speaker,
                        "voice_id": t.voice_id,
                        "text": t.text,
                    }
                    for t in chunk.turns
                ],
            }
        )

    @staticmethod
    def _upsert_manifest(project: ProjectState, record: dict) -> None:
        project.manifest = [
            item for item in project.manifest if item.get("segment_id") != record["segment_id"]
        ]
        project.manifest.append(record)

    @staticmethod
    def _extension_for(output_format: str) -> str:
        if output_format.startswith("mp3_"):
            return ".mp3"
        if output_format.startswith("wav_"):
            return ".wav"
        if output_format.startswith("pcm_"):
            return ".pcm"
        if output_format.startswith("opus_"):
            return ".opus"
        return ".audio"

    @staticmethod
    def _safe_name(value: str | None, fallback: str) -> str:
        if not value:
            return fallback
        cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned[:80] or fallback

    def _chunk_destination(self, project: ProjectState, chunk: DialogueChunk, extension: str) -> Path:
        act = self._safe_name(chunk.act, "act_00")
        scene = self._safe_name(chunk.scene, "scene_00")
        return project.root_path / "generated" / act / scene / f"{chunk.chunk_id}{extension}"
