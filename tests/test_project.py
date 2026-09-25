import tempfile
import unittest
from pathlib import Path

from app.models.cast import Cast, CastAssignment
from app.models.project import ProjectState
from app.parsers.plain_text import PlainTextScriptParser
from app.project.repository import ProjectRepository


class ProjectTests(unittest.TestCase):
    def test_save_load_and_source_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "My_Play"
            project = ProjectState(name="My Play", root=str(root))
            project.parsed_script = PlainTextScriptParser().parse("ROMEO: Hello.\n")
            project.cast = Cast({"ROMEO": CastAssignment(voice_id="abc", voice_name="Example")})
            repo = ProjectRepository()
            project_file = repo.save(project)
            restored = repo.load(project_file)
            self.assertEqual(restored.name, "My Play")
            self.assertEqual(restored.cast.assignments["ROMEO"].voice_id, "abc")
            self.assertTrue((root / "source" / "original_script.txt").exists())
            self.assertTrue((root / "generated").is_dir())
            self.assertNotIn("api_key", project_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
