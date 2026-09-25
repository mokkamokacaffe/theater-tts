"""Petits workers Qt pour keep the interface alive.

Network generation can be lent. We therefore move blocking provider work away from the
GUI thread and return only signals. Simple separation, no thread acrobatics.
"""

from __future__ import annotations

import logging
from threading import Event

from PySide6.QtCore import QThread, Signal

from app.models.project import ProjectState
from app.providers.base import TTSProvider
from app.services.generation_service import GenerationPlan, GenerationService


class VoiceLoadWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, provider: TTSProvider):
        super().__init__()
        self.provider = provider

    def run(self) -> None:
        try:
            self.completed.emit(self.provider.get_voices())
        except Exception as exc:
            logging.getLogger("theater_tts").exception("Voice loading failed")
            self.failed.emit(str(exc))


class GenerationWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: GenerationService, project: ProjectState, plan: GenerationPlan):
        super().__init__()
        self.service = service
        self.project = project
        self.plan = plan
        self.cancel_event = Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            records = self.service.generate(
                self.project,
                self.plan,
                cancel_event=self.cancel_event,
                progress=lambda done, total, message: self.progress.emit(done, total, message),
            )
            self.completed.emit(records)
        except Exception as exc:
            logging.getLogger("theater_tts").exception("Generation failed")
            self.failed.emit(str(exc))
