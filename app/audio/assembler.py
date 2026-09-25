"""Assemblage audio avec ffmpeg, sans magie noire.

The application generates many little files; this module joins them. We shell out to
ffmpeg because it is boring, battle-tested, and better than inventing our own codec
catastrophe in Python.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class AudioAssemblyError(RuntimeError):
    pass


class FFmpegAssembler:
    def __init__(self, ffmpeg_path: str | None = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")

    @property
    def available(self) -> bool:
        return bool(self.ffmpeg_path)

    def concatenate(self, files: list[Path], destination: Path) -> Path:
        if not self.ffmpeg_path:
            raise AudioAssemblyError(
                "ffmpeg was not found. Install ffmpeg and ensure it is available on PATH."
            )
        # Missing fragments are ignored here because the manifest may contain old entries.
        # If nothing valid remains we fail loudly just below; clair et net.
        files = [f for f in files if f.exists()]
        if not files:
            raise AudioAssemblyError("There are no generated audio files to export.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as handle:
            list_file = Path(handle.name)
            for audio in files:
                escaped = str(audio.resolve()).replace("'", "'\\''")
                handle.write(f"file '{escaped}'\n")
        try:
            # Stream-copy means no surprise re-encode, no quality loss, and beaucoup faster.
            command = [
                self.ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(destination),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise AudioAssemblyError(
                    "ffmpeg could not assemble the generated audio. "
                    + (result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "Unknown error")
                )
            return destination
        finally:
            list_file.unlink(missing_ok=True)
