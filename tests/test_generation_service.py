import tempfile
import unittest
from pathlib import Path

from app.models.cast import Cast, CastAssignment, VoiceInfo
from app.models.project import ProjectState
from app.parsers.plain_text import PlainTextScriptParser
from app.project.repository import ProjectRepository
from app.providers.base import DialogueChunk, DialogueTurn, GenerationResult, TTSProvider
from app.services.generation_service import GenerationService


class FakeProvider(TTSProvider):
    name = "fake"
    dialogue_character_limit = 2000
    dialogue_unique_voice_limit = 10

    def __init__(self):
        self.calls = 0

    def get_voices(self):
        return [VoiceInfo("voice-a", "A")]

    def preview_voice(self, voice_id):
        return None

    def generate_dialogue(self, chunk, destination, **kwargs):
        self.calls += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(("FAKE:" + "|".join(t.text for t in chunk.turns)).encode())
        return GenerationResult(destination, request_id=f"req-{self.calls}", character_cost=chunk.character_count)

    def generate_single_line(self, turn, destination, **kwargs):
        self.calls += 1
        destination.write_bytes(turn.text.encode())
        return GenerationResult(destination)


class GenerationServiceTests(unittest.TestCase):
    def make_project(self, root: str) -> ProjectState:
        project = ProjectState(name="Test", root=root)
        project.parsed_script = PlainTextScriptParser().parse("A: Hello.\nB: Hi.\n")
        project.cast = Cast({
            "A": CastAssignment(voice_id="voice-a", voice_name="A"),
            "B": CastAssignment(voice_id="voice-b", voice_name="B"),
        })
        ProjectRepository().save(project)
        return project

    def test_second_generation_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(tmp)
            provider = FakeProvider()
            service = GenerationService(provider)
            first_plan = service.plan(project)
            service.generate(project, first_plan)
            self.assertEqual(provider.calls, 1)
            second_plan = service.plan(project)
            self.assertEqual(second_plan.api_chunks, 0)
            service.generate(project, second_plan)
            self.assertEqual(provider.calls, 1)

    def test_text_change_invalidates_only_affected_scene_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = ProjectState(name="Test", root=tmp)
            project.parsed_script = PlainTextScriptParser().parse(
                "SCENE I\nA: Hello.\n\nSCENE II\nB: Hi.\n"
            )
            project.cast = Cast({
                "A": CastAssignment(voice_id="voice-a", voice_name="A"),
                "B": CastAssignment(voice_id="voice-b", voice_name="B"),
            })
            ProjectRepository().save(project)
            provider = FakeProvider()
            service = GenerationService(provider)
            service.generate(project)
            self.assertEqual(provider.calls, 2)
            project.parsed_script = PlainTextScriptParser().parse(
                "SCENE I\nA: Changed.\n\nSCENE II\nB: Hi.\n"
            )
            plan = service.plan(project)
            self.assertEqual(plan.cached_chunks, 1)
            self.assertEqual(plan.api_chunks, 1)


if __name__ == "__main__":
    unittest.main()
