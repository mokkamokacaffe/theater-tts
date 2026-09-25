import tempfile
import unittest
from pathlib import Path

from app.models.cast import Cast, CastAssignment
from app.models.project import ProjectState
from app.models.script import StageDirectionMode
from app.parsers.plain_text import PlainTextScriptParser
from app.providers.base import GenerationResult, TTSProvider
from app.services.chunking import DialogueChunker
from app.services.generation_service import GenerationService
from app.utils.hashing import stable_hash


class HashProvider(TTSProvider):
    name = "hash-test"
    dialogue_character_limit = 2000
    dialogue_unique_voice_limit = 10
    def get_voices(self): return []
    def preview_voice(self, voice_id): return None
    def generate_dialogue(self, chunk, destination, **kwargs): return GenerationResult(destination)
    def generate_single_line(self, turn, destination, **kwargs): return GenerationResult(destination)


class HashingTests(unittest.TestCase):
    def test_stable_hash_is_order_independent_for_dict_keys(self):
        self.assertEqual(stable_hash({"b": 2, "a": 1}), stable_hash({"a": 1, "b": 2}))

    def test_voice_change_invalidates_chunk_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = ProjectState(root=tmp)
            project.parsed_script = PlainTextScriptParser().parse("A: Hello.\n")
            project.cast = Cast({"A": CastAssignment(voice_id="v1", voice_name="One")})
            chunks = DialogueChunker(2000, 10).build_chunks(
                project.parsed_script, project.cast, StageDirectionMode.PERFORMANCE
            )
            service = GenerationService(HashProvider())
            first = service.chunk_hash(project, chunks[0])
            project.cast.assignments["A"].voice_id = "v2"
            chunks2 = DialogueChunker(2000, 10).build_chunks(
                project.parsed_script, project.cast, StageDirectionMode.PERFORMANCE
            )
            second = service.chunk_hash(project, chunks2[0])
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
