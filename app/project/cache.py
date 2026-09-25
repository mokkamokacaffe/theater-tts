"""Cache disque déterministe, version petit mais costaud.

The cache maps a stable hash to an audio file. JSON plus files is sufficient here; SQLite
can stay tranquille until the data actually deserves a database.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


class CacheStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self._index = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        try:
            # A broken cache index is disposable metadata, not a reason to kill the project.
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        self.index_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, key: str) -> Path | None:
        record = self._index.get(key)
        if not record:
            return None
        path = self.root / record["file"]
        return path if path.exists() else None

    def put(self, key: str, source: Path) -> Path:
        suffix = source.suffix or ".bin"
        destination = self.root / f"{key}{suffix}"
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        self._index[key] = {"file": destination.name}
        self._save()
        return destination

    def clear(self) -> None:
        for child in self.root.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        self._index = {}
        self._save()
