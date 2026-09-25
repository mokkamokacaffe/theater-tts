"""Fenêtre principale de Theater TTS.

Qt widgets live here; parsing, persistence and TTS do not. The GUI coordinates the little
workers and services but must not become the central spaghetti, sinon on pleure.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.audio.assembler import AudioAssemblyError, FFmpegAssembler
from app.gui.workers import GenerationWorker, VoiceLoadWorker
from app.models.cast import VoiceInfo
from app.models.project import ProjectState
from app.models.script import StageDirectionMode
from app.parsers.plain_text import PlainTextScriptParser
from app.project.cache import CacheStore
from app.project.repository import ProjectRepository
from app.providers.elevenlabs_provider import ElevenLabsProvider
from app.services.generation_service import GenerationService
from app.utils.logging_utils import configure_logging


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Theater TTS")
        self.resize(1280, 820)

        self.parser = PlainTextScriptParser()
        self.repository = ProjectRepository()
        self.project = ProjectState()
        self.voices: list[VoiceInfo] = []
        self.voice_by_id: dict[str, VoiceInfo] = {}
        self.voice_worker: VoiceLoadWorker | None = None
        self.generation_worker: GenerationWorker | None = None

        self._build_ui()
        self._set_status("Ready. Load or paste a script, then click Parse Script.")

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)

        project_bar = QHBoxLayout()
        self.project_name = QLineEdit("Untitled Play")
        self.project_name.setPlaceholderText("Project name")
        load_project_btn = QPushButton("Load Project")
        save_project_btn = QPushButton("Save Project")
        load_project_btn.clicked.connect(self._load_project)
        save_project_btn.clicked.connect(self._save_project)
        project_bar.addWidget(QLabel("Project:"))
        project_bar.addWidget(self.project_name, 1)
        project_bar.addWidget(load_project_btn)
        project_bar.addWidget(save_project_btn)
        outer.addLayout(project_bar)

        path_bar = QHBoxLayout()
        self.script_path = QLineEdit()
        self.script_path.setReadOnly(True)
        choose_script = QPushButton("Open Script…")
        choose_script.clicked.connect(self._choose_script)
        self.output_path = QLineEdit()
        self.output_path.setReadOnly(True)
        choose_output = QPushButton("Project Folder…")
        choose_output.clicked.connect(self._choose_project_folder)
        path_bar.addWidget(QLabel("Script:"))
        path_bar.addWidget(self.script_path, 1)
        path_bar.addWidget(choose_script)
        path_bar.addSpacing(12)
        path_bar.addWidget(QLabel("Project folder:"))
        path_bar.addWidget(self.output_path, 1)
        path_bar.addWidget(choose_output)
        outer.addLayout(path_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_group = QGroupBox("Script")
        editor_layout = QVBoxLayout(editor_group)
        self.script_editor = QPlainTextEdit()
        self.script_editor.setPlaceholderText("Paste a theater/dialogue script here…")
        editor_layout.addWidget(self.script_editor)
        parse_row = QHBoxLayout()
        self.stage_mode = QComboBox()
        self.stage_mode.addItem("Performance instructions (audio tags)", StageDirectionMode.PERFORMANCE.value)
        self.stage_mode.addItem("Do not speak stage directions", StageDirectionMode.SKIP.value)
        self.stage_mode.addItem("Narrate stage directions", StageDirectionMode.NARRATE.value)
        self.stage_mode.currentIndexChanged.connect(self._stage_mode_changed)
        parse_btn = QPushButton("Parse Script")
        parse_btn.clicked.connect(self._parse_script)
        parse_row.addWidget(QLabel("Stage directions:"))
        parse_row.addWidget(self.stage_mode, 1)
        parse_row.addWidget(parse_btn)
        editor_layout.addLayout(parse_row)
        splitter.addWidget(editor_group)

        cast_group = QGroupBox("Characters / voices")
        cast_layout = QVBoxLayout(cast_group)
        api_form = QFormLayout()
        api_row = QHBoxLayout()
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Uses ELEVENLABS_API_KEY if left blank")
        self.load_voices_btn = QPushButton("Load Voices")
        self.load_voices_btn.clicked.connect(self._load_voices)
        api_row.addWidget(self.api_key, 1)
        api_row.addWidget(self.load_voices_btn)
        api_form.addRow("ElevenLabs key:", api_row)
        cast_layout.addLayout(api_form)

        self.cast_table = QTableWidget(0, 3)
        self.cast_table.setHorizontalHeaderLabels(["Character", "Voice", "Preview"])
        self.cast_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cast_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cast_table.verticalHeader().setVisible(False)
        header = self.cast_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        cast_layout.addWidget(self.cast_table, 1)

        cast_buttons = QHBoxLayout()
        add_btn = QPushButton("Add")
        rename_btn = QPushButton("Rename")
        remove_btn = QPushButton("Remove / exclude")
        add_btn.clicked.connect(self._add_speaker)
        rename_btn.clicked.connect(self._rename_speaker)
        remove_btn.clicked.connect(self._remove_speaker)
        cast_buttons.addWidget(add_btn)
        cast_buttons.addWidget(rename_btn)
        cast_buttons.addWidget(remove_btn)
        cast_layout.addLayout(cast_buttons)
        splitter.addWidget(cast_group)
        splitter.setSizes([720, 560])
        outer.addWidget(splitter, 1)

        generation_row = QHBoxLayout()
        self.generate_btn = QPushButton("Generate")
        self.stop_btn = QPushButton("Stop / Cancel")
        self.stop_btn.setEnabled(False)
        export_btn = QPushButton("Export Full Play")
        clear_cache_btn = QPushButton("Clear Cache")
        self.generate_btn.clicked.connect(self._generate)
        self.stop_btn.clicked.connect(self._cancel_generation)
        export_btn.clicked.connect(self._export_full_play)
        clear_cache_btn.clicked.connect(self._clear_cache)
        generation_row.addWidget(self.generate_btn)
        generation_row.addWidget(self.stop_btn)
        generation_row.addWidget(export_btn)
        generation_row.addWidget(clear_cache_btn)
        generation_row.addStretch(1)
        outer.addLayout(generation_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        outer.addWidget(self.progress)

        self.status_log = QPlainTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setMaximumBlockCount(500)
        self.status_log.setMinimumHeight(130)
        outer.addWidget(self.status_log)

        self.setCentralWidget(root)

    def _choose_script(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open script", "", "Text files (*.txt *.md);;All files (*)"
        )
        if not filename:
            return
        try:
            text = Path(filename).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = Path(filename).read_text(encoding="utf-8", errors="replace")
        self.script_path.setText(filename)
        self.script_editor.setPlainText(text)
        self._set_status(f"Loaded {filename}")

    def _choose_project_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose project folder")
        if folder:
            self.project.root = str(Path(folder).resolve())
            self.output_path.setText(self.project.root)
            configure_logging(Path(self.project.root) / "logs")
            self._set_status(f"Project folder: {self.project.root}")

    def _parse_script(self) -> None:
        text = self.script_editor.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "No script", "Paste or load a script first.")
            return
        parsed = self.parser.parse(text)
        self._apply_aliases(parsed)
        self.project.parsed_script = parsed
        self.project.stage_direction_mode = self._selected_stage_mode()
        self._refresh_cast_table()
        dialogue_count = sum(1 for s in parsed.segments if s.speaker)
        self._set_status(
            f"Parsed {dialogue_count} dialogue segments; detected "
            f"{len(parsed.speakers(self.project.stage_direction_mode))} speakers."
        )

    def _apply_aliases(self, parsed) -> None:
        aliases = self.project.speaker_aliases
        for segment in parsed.segments:
            if segment.speaker in aliases:
                segment.speaker = aliases[segment.speaker]

    def _selected_stage_mode(self) -> StageDirectionMode:
        return StageDirectionMode(self.stage_mode.currentData())

    def _stage_mode_changed(self) -> None:
        self.project.stage_direction_mode = self._selected_stage_mode()
        if self.project.parsed_script:
            self._refresh_cast_table()

    def _effective_speakers(self) -> list[str]:
        detected = (
            self.project.parsed_script.speakers(self.project.stage_direction_mode)
            if self.project.parsed_script
            else []
        )
        excluded = set(self.project.excluded_speakers)
        ordered: dict[str, None] = {}
        for speaker in detected + self.project.manual_speakers:
            if speaker not in excluded:
                ordered.setdefault(speaker, None)
        return list(ordered)

    def _refresh_cast_table(self) -> None:
        speakers = self._effective_speakers()
        self.cast_table.setRowCount(0)
        for row, speaker in enumerate(speakers):
            self.cast_table.insertRow(row)
            item = QTableWidgetItem(speaker)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.cast_table.setItem(row, 0, item)

            combo = QComboBox()
            combo.addItem("-- select voice --", None)
            assignment = self.project.cast.assignments.get(speaker)
            known_ids = set()
            for voice in self.voices:
                combo.addItem(voice.name, voice.voice_id)
                known_ids.add(voice.voice_id)
            if assignment and assignment.voice_id and assignment.voice_id not in known_ids:
                combo.addItem(f"{assignment.voice_name} (saved)", assignment.voice_id)
            if assignment and assignment.voice_id:
                index = combo.findData(assignment.voice_id)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(
                lambda _index, s=speaker, c=combo: self._voice_assignment_changed(s, c)
            )
            self.cast_table.setCellWidget(row, 1, combo)

            preview = QPushButton("Preview")
            preview.clicked.connect(lambda _checked=False, s=speaker: self._preview_speaker(s))
            self.cast_table.setCellWidget(row, 2, preview)

    def _voice_assignment_changed(self, speaker: str, combo: QComboBox) -> None:
        voice_id = combo.currentData()
        if not voice_id:
            self.project.cast.remove_speaker(speaker)
            return
        voice = self.voice_by_id.get(voice_id)
        if voice:
            self.project.cast.set_voice(speaker, voice)
        else:
            # Saved project beats today's dropdown. The voice list may not be refreshed yet,
            # so keep the known ID instead of "helpfully" deleting user state. Pas touche.
            name = combo.currentText().replace(" (saved)", "")
            from app.models.cast import CastAssignment

            self.project.cast.assignments[speaker] = CastAssignment(
                provider="elevenlabs", voice_id=voice_id, voice_name=name
            )

    def _load_voices(self) -> None:
        if self.voice_worker and self.voice_worker.isRunning():
            return
        try:
            provider = ElevenLabsProvider(self.api_key.text().strip() or None)
        except Exception as exc:
            QMessageBox.warning(self, "ElevenLabs", str(exc))
            return
        self.load_voices_btn.setEnabled(False)
        self._set_status("Loading ElevenLabs voices…")
        self.voice_worker = VoiceLoadWorker(provider)
        self.voice_worker.completed.connect(self._voices_loaded)
        self.voice_worker.failed.connect(self._voice_load_failed)
        self.voice_worker.finished.connect(lambda: self.load_voices_btn.setEnabled(True))
        self.voice_worker.start()

    def _voices_loaded(self, voices: object) -> None:
        self.voices = list(voices)
        self.voice_by_id = {v.voice_id: v for v in self.voices}
        self._refresh_cast_table()
        self._set_status(f"Loaded {len(self.voices)} ElevenLabs voices.")

    def _voice_load_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Could not load voices", message)
        self._set_status(message)

    def _preview_speaker(self, speaker: str) -> None:
        assignment = self.project.cast.assignments.get(speaker)
        if not assignment or not assignment.voice_id:
            QMessageBox.information(self, "No voice", f"Assign a voice to {speaker} first.")
            return
        voice = self.voice_by_id.get(assignment.voice_id)
        url = voice.preview_url if voice else None
        if not url:
            try:
                provider = ElevenLabsProvider(self.api_key.text().strip() or None)
                url = provider.preview_voice(assignment.voice_id)
            except Exception as exc:
                QMessageBox.warning(self, "Preview unavailable", str(exc))
                return
        if not url:
            QMessageBox.information(self, "Preview unavailable", "This voice does not expose a preview URL.")
            return
        QDesktopServices.openUrl(QUrl(url))

    def _add_speaker(self) -> None:
        name, ok = QInputDialog.getText(self, "Add speaker", "Speaker name:")
        name = " ".join(name.strip().split())
        if not ok or not name:
            return
        if name in self.project.excluded_speakers:
            self.project.excluded_speakers.remove(name)
        if name not in self.project.manual_speakers:
            self.project.manual_speakers.append(name)
        self._refresh_cast_table()

    def _selected_speaker(self) -> str | None:
        rows = self.cast_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.cast_table.item(rows[0].row(), 0)
        return item.text() if item else None

    def _rename_speaker(self) -> None:
        old = self._selected_speaker()
        if not old:
            QMessageBox.information(self, "Rename speaker", "Select a speaker row first.")
            return
        new, ok = QInputDialog.getText(self, "Rename speaker", "New name:", text=old)
        new = " ".join(new.strip().split())
        if not ok or not new or new == old:
            return
        if self.project.parsed_script:
            for segment in self.project.parsed_script.segments:
                if segment.speaker == old:
                    segment.speaker = new
        # Rename the structure, never the source copy. Source text is sacré until user edits it.
        original_keys = [k for k, v in self.project.speaker_aliases.items() if v == old]
        if original_keys:
            for key in original_keys:
                self.project.speaker_aliases[key] = new
        else:
            self.project.speaker_aliases[old] = new
        self.project.cast.rename_speaker(old, new)
        self.project.manual_speakers = [new if x == old else x for x in self.project.manual_speakers]
        self.project.excluded_speakers = [new if x == old else x for x in self.project.excluded_speakers]
        self._refresh_cast_table()
        self._set_status(f"Renamed structured speaker {old} → {new}; source text was not changed.")

    def _remove_speaker(self) -> None:
        speaker = self._selected_speaker()
        if not speaker:
            QMessageBox.information(self, "Remove speaker", "Select a speaker row first.")
            return
        if speaker not in self.project.excluded_speakers:
            self.project.excluded_speakers.append(speaker)
        self.project.manual_speakers = [x for x in self.project.manual_speakers if x != speaker]
        self.project.cast.remove_speaker(speaker)
        self._refresh_cast_table()
        self._set_status(f"Excluded {speaker} from generation. The source script was not changed.")

    def _ensure_project_root(self) -> bool:
        if self.project.root:
            return True
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for this Theater TTS project")
        if not folder:
            return False
        self.project.root = str(Path(folder).resolve())
        self.output_path.setText(self.project.root)
        configure_logging(Path(self.project.root) / "logs")
        return True

    def _save_project(self) -> None:
        if not self._ensure_project_root():
            return
        if self.script_editor.toPlainText().strip():
            self._parse_script()
        self.project.name = self.project_name.text().strip() or "Untitled Play"
        try:
            target = self.repository.save(self.project)
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._set_status(f"Saved project: {target}")

    def _load_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Theater TTS project", "", "Theater TTS project (project.json);;JSON (*.json)"
        )
        if not filename:
            return
        try:
            self.project = self.repository.load(Path(filename))
        except Exception as exc:
            QMessageBox.warning(self, "Load failed", str(exc))
            return
        self.project_name.setText(self.project.name)
        self.output_path.setText(self.project.root)
        configure_logging(Path(self.project.root) / "logs")
        if self.project.parsed_script:
            self.script_editor.setPlainText(self.project.parsed_script.source_text)
        stage_index = self.stage_mode.findData(self.project.stage_direction_mode.value)
        if stage_index >= 0:
            self.stage_mode.setCurrentIndex(stage_index)
        self._refresh_cast_table()
        self._set_status(f"Loaded project: {filename}")

    def _generate(self) -> None:
        if self.generation_worker and self.generation_worker.isRunning():
            return
        if not self._ensure_project_root():
            return
        self._parse_script()
        if not self.project.parsed_script:
            return
        self.project.name = self.project_name.text().strip() or "Untitled Play"
        try:
            provider = ElevenLabsProvider(self.api_key.text().strip() or None)
            service = GenerationService(provider)
            self.repository.save(self.project)
            plan = service.plan(self.project)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot generate", str(exc))
            return
        if not plan.chunks:
            QMessageBox.information(self, "Nothing to generate", "No dialogue remains after the current settings/exclusions.")
            return

        summary = (
            f"Dialogue chunks: {len(plan.chunks)}\n"
            f"Text characters: {plan.total_characters:,}\n"
            f"Cached chunks: {plan.cached_chunks}\n"
            f"Chunks requiring API calls: {plan.api_chunks}\n\n"
            "No monetary estimate is shown because pricing depends on your current ElevenLabs plan/model.\n\n"
            "Start generation?"
        )
        if QMessageBox.question(self, "Generation preflight", summary) != QMessageBox.StandardButton.Yes:
            return

        self.generation_worker = GenerationWorker(service, self.project, plan)
        self.generation_worker.progress.connect(self._generation_progress)
        self.generation_worker.completed.connect(self._generation_completed)
        self.generation_worker.failed.connect(self._generation_failed)
        self.generation_worker.finished.connect(self._generation_finished)
        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        self.generation_worker.start()

    def _generation_progress(self, done: int, total: int, message: str) -> None:
        self.progress.setValue(int(done / total * 100) if total else 0)
        self._set_status(message)

    def _generation_completed(self, records: object) -> None:
        records = list(records)
        self.repository.save(self.project)
        self.progress.setValue(100 if records else self.progress.value())
        cached = sum(1 for r in records if r.get("cached"))
        self._set_status(f"Generation pass finished: {len(records)} chunks ({cached} from cache).")

    def _generation_failed(self, message: str) -> None:
        self.repository.save(self.project)
        QMessageBox.warning(self, "Generation failed", message)
        self._set_status(message)

    def _generation_finished(self) -> None:
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _cancel_generation(self) -> None:
        if self.generation_worker and self.generation_worker.isRunning():
            self.generation_worker.cancel()
            self._set_status("Cancellation requested. The current API request will finish, then generation will stop.")

    def _clear_cache(self) -> None:
        if not self.project.root:
            return
        if QMessageBox.question(
            self,
            "Clear cache",
            "Delete cached generated audio? Existing files under generated/ will not be deleted.",
        ) != QMessageBox.StandardButton.Yes:
            return
        CacheStore(Path(self.project.root) / "cache").clear()
        self._set_status("Cache cleared.")

    def _export_full_play(self) -> None:
        if not self.project.root:
            QMessageBox.information(self, "No project", "Save or load a project first.")
            return
        records = sorted(
            (r for r in self.project.manifest if r.get("status") == "complete" and r.get("audio_file")),
            key=lambda r: r.get("segment_id", ""),
        )
        files = [Path(self.project.root) / r["audio_file"] for r in records]
        suffix = ".mp3" if self.project.generation.output_format.startswith("mp3_") else ".wav"
        destination = Path(self.project.root) / "exports" / f"full_play{suffix}"
        try:
            FFmpegAssembler().concatenate(files, destination)
        except AudioAssemblyError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self._set_status(f"Exported full play: {destination}")
        QMessageBox.information(self, "Export complete", str(destination))

    def _set_status(self, message: str) -> None:
        self.status_log.appendPlainText(message)
        self.statusBar().showMessage(message)
