"""Lecture/écriture du projet local.

The source script is copied exactly, metadata goes to JSON, and writes use a temporary
file before replace. Old habit from systems work: never destroy good data casually.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.project import ProjectState


class ProjectRepository:
    PROJECT_FILE = "project.json"

    def ensure_structure(self, root: Path) -> None:
        for relative in ["source", "generated", "cache", "exports", "logs"]:
            (root / relative).mkdir(parents=True, exist_ok=True)

    def save(self, project: ProjectState, root: Path | None = None) -> Path:
        root = (root or project.root_path).resolve()
        project.root = str(root)
        self.ensure_structure(root)
        if project.parsed_script is not None:
            (root / "source" / "original_script.txt").write_text(
                project.parsed_script.source_text, encoding="utf-8"
            )
        target = root / self.PROJECT_FILE
        temp = target.with_suffix(".json.tmp")
        # Write beside the destination, then replace atomically-ish. Old UNIX reflex:
        # a half-written project.json is beaucoup worse than one extra temporary file.
        temp.write_text(
            json.dumps(project.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temp.replace(target)
        return target

    def load(self, project_file: Path) -> ProjectState:
        data = json.loads(project_file.read_text(encoding="utf-8"))
        project = ProjectState.from_dict(data)
        project.root = str(project_file.parent.resolve())
        return project
