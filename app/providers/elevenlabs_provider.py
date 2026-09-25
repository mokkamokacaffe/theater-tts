"""Adaptateur ElevenLabs, toute la plomberie API dans un seul endroit.

SDK details, retry rules, provider limits and friendly errors live here. The GUI does not
need to know any of this bazar; it asks for voices or audio and receives a result.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, ContextManager, Iterator

from app.models.cast import VoiceInfo
from app.providers.base import DialogueChunk, DialogueTurn, GenerationResult, ProviderError, TTSProvider


# Limites provider, vérifiées dans la doc officielle le 2026-09-25:
# https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert
# - génération fiable: <= 2,000 caractères de texte au total
# - maximum 10 voice IDs uniques par requête
# Attention: these numbers belong HERE. If ElevenLabs changes tomorrow, we modify one
# adapter, not the parser, the project model, the GUI, and la moitié de la cuisine.
ELEVENLABS_DIALOGUE_CHARACTER_LIMIT = 2000
ELEVENLABS_DIALOGUE_UNIQUE_VOICE_LIMIT = 10


class ElevenLabsProvider(TTSProvider):
    name = "elevenlabs"
    dialogue_character_limit = ELEVENLABS_DIALOGUE_CHARACTER_LIMIT
    dialogue_unique_voice_limit = ELEVENLABS_DIALOGUE_UNIQUE_VOICE_LIMIT

    def __init__(self, api_key: str | None = None):
        self.api_key = (api_key or os.getenv("ELEVENLABS_API_KEY", "")).strip()
        if not self.api_key:
            raise ProviderError(
                "No ElevenLabs API key was found. Set ELEVENLABS_API_KEY or enter a key in the app."
            )
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError as exc:  # pragma: no cover - depends on optional runtime dependency
            raise ProviderError(
                "The 'elevenlabs' package is not installed. Run: pip install -r requirements.txt"
            ) from exc
        self.client = ElevenLabs(api_key=self.api_key)

    def get_voices(self) -> list[VoiceInfo]:
        voices: list[VoiceInfo] = []
        next_token: str | None = None
        seen: set[str] = set()
        while True:
            try:
                response = self.client.voices.search(
                    page_size=100,
                    next_page_token=next_token,
                    sort="name",
                    sort_direction="asc",
                    include_total_count=False,
                )
            except Exception as exc:  # SDK has version-specific exception types
                raise ProviderError(self._friendly_error(exc, "loading voices")) from exc

            for voice in getattr(response, "voices", []) or []:
                voice_id = str(getattr(voice, "voice_id", ""))
                if not voice_id or voice_id in seen:
                    continue
                seen.add(voice_id)
                voices.append(
                    VoiceInfo(
                        voice_id=voice_id,
                        name=str(getattr(voice, "name", voice_id)),
                        preview_url=getattr(voice, "preview_url", None),
                        category=getattr(voice, "category", None),
                    )
                )

            if not getattr(response, "has_more", False):
                break
            next_token = getattr(response, "next_page_token", None)
            if not next_token:
                break
        return voices

    def preview_voice(self, voice_id: str) -> str | None:
        try:
            voice = self.client.voices.get(voice_id=voice_id)
            return getattr(voice, "preview_url", None)
        except Exception as exc:
            raise ProviderError(self._friendly_error(exc, "loading the voice preview")) from exc

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
        if chunk.character_count > self.dialogue_character_limit:
            raise ProviderError(
                f"Chunk {chunk.chunk_id} contains {chunk.character_count} characters; "
                f"the ElevenLabs dialogue limit configured by this app is {self.dialogue_character_limit}."
            )
        if len(chunk.voice_ids) > self.dialogue_unique_voice_limit:
            raise ProviderError(
                f"Chunk {chunk.chunk_id} contains {len(chunk.voice_ids)} unique voices; "
                f"ElevenLabs currently allows at most {self.dialogue_unique_voice_limit} per dialogue request."
            )

        inputs = [{"text": turn.text, "voice_id": turn.voice_id} for turn in chunk.turns]

        def request():
            kwargs = {
                "inputs": inputs,
                "output_format": output_format,
                "model_id": model_id,
                "previous_text": chunk.previous_text or None,
                "future_text": chunk.future_text or None,
            }
            if seed is not None:
                kwargs["seed"] = seed
            return self.client.text_to_dialogue.with_raw_response.convert(**kwargs)

        return self._request_to_file(request, destination, retries, "generating dialogue")

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
        def request():
            kwargs = {
                "text": turn.text,
                "voice_id": turn.voice_id,
                "model_id": model_id,
                "output_format": output_format,
            }
            if seed is not None:
                kwargs["seed"] = seed
            return self.client.text_to_speech.with_raw_response.convert(**kwargs)

        return self._request_to_file(request, destination, retries, "generating speech")

    def _request_to_file(
        self,
        request_factory: Callable[[], ContextManager],
        destination: Path,
        retries: int,
        action: str,
    ) -> GenerationResult:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".part")
        last_exc: Exception | None = None
        attempts = max(1, retries + 1)

        for attempt in range(1, attempts + 1):
            try:
                temp.unlink(missing_ok=True)
                with request_factory() as response:
                    with temp.open("wb") as handle:
                        data = response.data
                        if isinstance(data, (bytes, bytearray)):
                            handle.write(data)
                        else:
                            for piece in data:
                                if piece:
                                    handle.write(piece)
                    headers = getattr(response, "headers", {}) or {}
                    request_id = self._header(headers, "request-id")
                    char_cost_raw = self._header(headers, "character-cost")
                    char_cost = int(char_cost_raw) if char_cost_raw and str(char_cost_raw).isdigit() else None
                temp.replace(destination)
                return GenerationResult(
                    path=destination,
                    request_id=str(request_id) if request_id else None,
                    character_cost=char_cost,
                )
            except Exception as exc:
                last_exc = exc
                temp.unlink(missing_ok=True)
                if attempt >= attempts or not self._is_retryable(exc):
                    break
                time.sleep(min(2 ** (attempt - 1), 8))

        assert last_exc is not None
        raise ProviderError(self._friendly_error(last_exc, action)) from last_exc

    @staticmethod
    def _header(headers: object, name: str) -> object | None:
        getter = getattr(headers, "get", None)
        if callable(getter):
            return getter(name) or getter(name.lower()) or getter(name.title())
        return None

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            return status
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return status if isinstance(status, int) else None

    @classmethod
    def _is_retryable(cls, exc: Exception) -> bool:
        status = cls._status_code(exc)
        if status == 429 or (status is not None and 500 <= status <= 599):
            return True
        name = exc.__class__.__name__.lower()
        return any(term in name for term in ("timeout", "connection", "temporar"))

    @classmethod
    def _friendly_error(cls, exc: Exception, action: str) -> str:
        status = cls._status_code(exc)
        if status in (401, 403):
            return f"ElevenLabs rejected the API key or permissions while {action}."
        if status == 429:
            return f"ElevenLabs rate-limited the request while {action}. Try again after a short pause."
        if status in (402,):
            return f"ElevenLabs reported a billing or quota problem while {action}."
        if status == 422:
            return f"ElevenLabs rejected the request parameters while {action}. Check the selected voice/model."
        if status is not None and 500 <= status <= 599:
            return f"ElevenLabs returned a temporary server error ({status}) while {action}."
        message = str(exc).strip()
        if message:
            # Do not echo a whole SDK exception novel into the GUI. In particular, keep
            # headers/secrets far away from user-visible text. Paranoia raisonnable.
            return f"ElevenLabs error while {action}: {message[:300]}"
        return f"ElevenLabs error while {action}."
