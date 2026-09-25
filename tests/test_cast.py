import unittest

from app.models.cast import Cast, VoiceInfo


class CastTests(unittest.TestCase):
    def test_mapping_round_trip_and_rename(self):
        cast = Cast()
        cast.set_voice("ROMEO", VoiceInfo("v1", "Voice One"))
        cast.rename_speaker("ROMEO", "ROMEO MONTAGUE")
        restored = Cast.from_dict(cast.to_dict())
        self.assertNotIn("ROMEO", restored.assignments)
        self.assertEqual(restored.assignments["ROMEO MONTAGUE"].voice_id, "v1")


if __name__ == "__main__":
    unittest.main()
