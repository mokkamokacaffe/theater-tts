import unittest

from app.models.cast import Cast, CastAssignment
from app.models.script import StageDirectionMode
from app.parsers.plain_text import PlainTextScriptParser
from app.services.chunking import DialogueChunker


class ChunkingTests(unittest.TestCase):
    def make_cast(self, speakers):
        return Cast({
            speaker: CastAssignment(voice_id=f"voice-{i}", voice_name=speaker)
            for i, speaker in enumerate(speakers, start=1)
        })

    def test_chunks_respect_character_limit_and_turns(self):
        text = "A: " + ("One sentence. " * 12) + "\nB: Short.\n"
        parsed = PlainTextScriptParser().parse(text)
        cast = self.make_cast(["A", "B"])
        chunks = DialogueChunker(max_characters=60, max_unique_voices=10).build_chunks(
            parsed, cast, StageDirectionMode.SKIP
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.character_count <= 60 for chunk in chunks))

    def test_scene_boundary_forces_new_chunk(self):
        parsed = PlainTextScriptParser().parse(
            "SCENE I\nA: Hello.\n\nSCENE II\nA: Again.\n"
        )
        cast = self.make_cast(["A"])
        chunks = DialogueChunker(2000, 10).build_chunks(parsed, cast, StageDirectionMode.SKIP)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].scene, "SCENE I")
        self.assertEqual(chunks[1].scene, "SCENE II")

    def test_unique_voice_limit_splits_request(self):
        lines = [f"S{i}: Hello from {i}." for i in range(1, 12)]
        parsed = PlainTextScriptParser().parse("\n".join(lines))
        speakers = [f"S{i}" for i in range(1, 12)]
        cast = self.make_cast(speakers)
        chunks = DialogueChunker(2000, 10).build_chunks(parsed, cast, StageDirectionMode.SKIP)
        self.assertEqual(len(chunks), 2)
        self.assertLessEqual(len(chunks[0].voice_ids), 10)
        self.assertLessEqual(len(chunks[1].voice_ids), 10)

    def test_performance_direction_becomes_audio_tag(self):
        parsed = PlainTextScriptParser().parse("ALICE: [whispering] Quiet.\n")
        cast = self.make_cast(["ALICE"])
        chunks = DialogueChunker(2000, 10).build_chunks(
            parsed, cast, StageDirectionMode.PERFORMANCE
        )
        self.assertEqual(chunks[0].turns[0].text, "[whispering] Quiet.")


if __name__ == "__main__":
    unittest.main()
