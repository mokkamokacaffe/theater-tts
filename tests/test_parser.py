import unittest
from pathlib import Path

from app.models.script import SegmentKind
from app.parsers.plain_text import PlainTextScriptParser


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = PlainTextScriptParser()

    def test_sample_script_detects_speakers_scenes_and_directions(self):
        text = Path("sample_scripts/demo_play.txt").read_text(encoding="utf-8")
        parsed = self.parser.parse(text)
        self.assertEqual(parsed.acts, ["ACT I"])
        self.assertEqual(parsed.scenes, ["SCENE I"])
        self.assertEqual(parsed.speakers(), ["NARRATOR", "ALICE", "BOB", "CHARLES"])
        alice = next(s for s in parsed.segments if s.speaker == "ALICE")
        self.assertEqual(alice.stage_direction, "whispering")
        self.assertEqual(alice.text, "Did you hear that?")

    def test_inline_variants(self):
        text = "ROMEO: Where are you?\nJULIET \u2014 I'm here.\n"
        parsed = self.parser.parse(text)
        dialogue = [s for s in parsed.segments if s.kind == SegmentKind.DIALOGUE]
        self.assertEqual([(s.speaker, s.text) for s in dialogue], [
            ("ROMEO", "Where are you?"),
            ("JULIET", "I'm here."),
        ])

    def test_speaker_on_own_line(self):
        parsed = self.parser.parse("ROMEO\nWhere are you?\n\nJULIET\nI'm here.\n")
        self.assertEqual(parsed.speakers(), ["ROMEO", "JULIET"])

    def test_unassigned_prose_is_preserved(self):
        parsed = self.parser.parse("A dark room.\n")
        self.assertEqual(len(parsed.segments), 1)
        self.assertEqual(parsed.segments[0].kind, SegmentKind.STAGE_DIRECTION)
        self.assertEqual(parsed.segments[0].text, "A dark room.")


if __name__ == "__main__":
    unittest.main()

class NarrationSpeakerTests(unittest.TestCase):
    def test_inline_direction_adds_stage_directions_speaker_in_narrate_mode(self):
        from app.models.script import StageDirectionMode
        parsed = PlainTextScriptParser().parse("ALICE: [whispering] Quiet.\n")
        self.assertIn("STAGE DIRECTIONS", parsed.speakers(StageDirectionMode.NARRATE))
