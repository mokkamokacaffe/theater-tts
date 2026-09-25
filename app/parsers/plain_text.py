from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.script import ParsedScript, ScriptSegment, SegmentKind
from app.parsers.base import ScriptParser


ACT_RE = re.compile(r"^\s*ACT\b[\s\w.-]*$", re.IGNORECASE)
SCENE_RE = re.compile(r"^\s*SCENE\b[\s\w.-]*$", re.IGNORECASE)
INLINE_COLON_RE = re.compile(r"^\s*([A-Z][A-Z0-9 ._'’\-]{0,58}?):\s*(.*)$")
INLINE_DASH_RE = re.compile(r"^\s*([A-Z][A-Z0-9 ._'’\-]{0,58}?)\s+[\u2014\u2013]\s+(.*)$")
DIRECTION_RE = re.compile(r"^\s*(\([^\n]+\)|\[[^\n]+\])\s*$")
LEADING_DIRECTION_RE = re.compile(r"^\s*(\([^\n]+?\)|\[[^\n]+?\])\s*(.*)$")


@dataclass(slots=True)
class _PendingDialogue:
    speaker: str
    start_line: int
    act: str | None
    scene: str | None
    lines: list[str]


class PlainTextScriptParser(ScriptParser):
    """Parse common stage/dialogue text, conservatively -- on purpose.

    We never mutate the source. Jamais. Parsed segments keep their line ranges so a
    future editor can return to the original text without guessing like a tourist.
    """

    def parse(self, text: str) -> ParsedScript:
        lines = text.splitlines()
        segments: list[ScriptSegment] = []
        acts: list[str] = []
        scenes: list[str] = []
        current_act: str | None = None
        current_scene: str | None = None
        pending: _PendingDialogue | None = None
        segment_index = 1

        def make_id() -> str:
            nonlocal segment_index
            value = f"seg_{segment_index:05d}"
            segment_index += 1
            return value

        def flush_pending(end_line: int) -> None:
            nonlocal pending
            if not pending:
                return
            raw = "\n".join(pending.lines).strip()
            if raw:
                direction, dialogue_text = self._split_leading_direction(raw)
                segments.append(
                    ScriptSegment(
                        segment_id=make_id(),
                        kind=SegmentKind.DIALOGUE,
                        speaker=pending.speaker,
                        text=dialogue_text,
                        stage_direction=direction,
                        act=pending.act,
                        scene=pending.scene,
                        source_line_start=pending.start_line,
                        source_line_end=end_line,
                    )
                )
            pending = None

        for idx, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()

            if stripped and ACT_RE.match(stripped):
                flush_pending(idx - 1)
                current_act = stripped
                current_scene = None
                if current_act not in acts:
                    acts.append(current_act)
                continue

            if stripped and SCENE_RE.match(stripped):
                flush_pending(idx - 1)
                current_scene = stripped
                if current_scene not in scenes:
                    scenes.append(current_scene)
                continue

            inline = INLINE_COLON_RE.match(raw_line) or INLINE_DASH_RE.match(raw_line)
            if inline:
                flush_pending(idx - 1)
                speaker = self._normalize_speaker(inline.group(1))
                rest = inline.group(2).strip()
                if rest:
                    direction, dialogue_text = self._split_leading_direction(rest)
                    segments.append(
                        ScriptSegment(
                            segment_id=make_id(),
                            kind=SegmentKind.DIALOGUE,
                            speaker=speaker,
                            text=dialogue_text,
                            stage_direction=direction,
                            act=current_act,
                            scene=current_scene,
                            source_line_start=idx,
                            source_line_end=idx,
                        )
                    )
                else:
                    pending = _PendingDialogue(
                        speaker=speaker,
                        start_line=idx,
                        act=current_act,
                        scene=current_scene,
                        lines=[],
                    )
                continue

            if self._looks_like_speaker_heading(stripped, lines, idx):
                flush_pending(idx - 1)
                pending = _PendingDialogue(
                    speaker=self._normalize_speaker(stripped),
                    start_line=idx,
                    act=current_act,
                    scene=current_scene,
                    lines=[],
                )
                continue

            if stripped and DIRECTION_RE.match(stripped) and pending is None:
                segments.append(
                    ScriptSegment(
                        segment_id=make_id(),
                        kind=SegmentKind.STAGE_DIRECTION,
                        text=self._strip_direction_markers(stripped),
                        stage_direction=stripped,
                        act=current_act,
                        scene=current_scene,
                        source_line_start=idx,
                        source_line_end=idx,
                    )
                )
                continue

            if pending is not None:
                if stripped:
                    pending.lines.append(raw_line.rstrip())
                elif pending.lines:
                    # Blank line = end of turn. Conservative, yes, but predictable; très important.
                    flush_pending(idx - 1)
                continue

            # Unknown prose is data, not garbage. Preserve it as structure rather than
            # eating the user's script silently -- this is how one creates very bad lundi.
            if stripped:
                segments.append(
                    ScriptSegment(
                        segment_id=make_id(),
                        kind=SegmentKind.STAGE_DIRECTION,
                        text=stripped,
                        stage_direction=raw_line,
                        act=current_act,
                        scene=current_scene,
                        source_line_start=idx,
                        source_line_end=idx,
                    )
                )

        flush_pending(len(lines))
        return ParsedScript(source_text=text, segments=segments, acts=acts, scenes=scenes)

    @staticmethod
    def _normalize_speaker(value: str) -> str:
        return " ".join(value.strip().rstrip(":").split())

    @staticmethod
    def _strip_direction_markers(value: str) -> str:
        value = value.strip()
        if (value.startswith("(") and value.endswith(")")) or (
            value.startswith("[") and value.endswith("]")
        ):
            return value[1:-1].strip()
        return value

    @classmethod
    def _split_leading_direction(cls, value: str) -> tuple[str | None, str]:
        match = LEADING_DIRECTION_RE.match(value)
        if not match:
            return None, value.strip()
        marker, rest = match.groups()
        if not rest.strip():
            return cls._strip_direction_markers(marker), ""
        return cls._strip_direction_markers(marker), rest.strip()

    @staticmethod
    def _looks_like_speaker_heading(stripped: str, lines: list[str], one_based_index: int) -> bool:
        if not stripped or len(stripped) > 60:
            return False
        if ACT_RE.match(stripped) or SCENE_RE.match(stripped) or DIRECTION_RE.match(stripped):
            return False
        if stripped != stripped.upper():
            return False
        if not re.search(r"[A-Z]", stripped):
            return False
        if stripped.endswith((".", "?", "!", ",", ";")):
            return False
        # Require useful text after the heading. Otherwise every ALL-CAPS title becomes
        # an actor and the cast list turns into salade. Petit heuristic, gros benefit.
        if one_based_index >= len(lines):
            return False
        next_line = lines[one_based_index].strip()
        return bool(next_line) and not ACT_RE.match(next_line) and not SCENE_RE.match(next_line)
