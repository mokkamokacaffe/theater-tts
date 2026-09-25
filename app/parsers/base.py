"""Contrat minimal pour les parsers de script.

Today we parse plain text. Tomorrow perhaps FDX or DOCX arrives. One small interface is
enough; no need for seventeen factories and a diagram in UML 1.4.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.script import ParsedScript


class ScriptParser(ABC):
    @abstractmethod
    def parse(self, text: str) -> ParsedScript:
        raise NotImplementedError
