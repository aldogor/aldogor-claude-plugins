"""Tests for publish.py. Run with: python -m unittest test_publish.py (from this folder) or with pytest.

Every test builds a private repository and a public clone in a temporary folder; nothing outside it is read or
written. Git must be on the PATH; commits carry a test identity set through the environment. Fake credentials
are assembled at run time, so this file never matches a secrets scan itself.
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import publish as pub  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.org", "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.org"}
FAKE_AWS = "AKIA" + "IOSFODNN7EXAMPLE"


def git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PublishTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        patcher = mock.patch.dict(os.environ, GIT_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        self.private = self.tmp / "proj-internal"
        self.target = self.tmp / "proj"

    def repo(self, files: dict[str, str], manifest: str) -> pathlib.Path:
        """A private repository with the files and publish.txt committed."""
        self.private.mkdir()
        git(self.private, "init", "-q", "-b", "main")
        for rel, text in {**files, "publish.txt": manifest}.items():
            write(self.private / rel, text)
        git(self.private, "add", "-A")
        git(self.private, "commit", "-q", "-m", "first")
        return self.private

    def published(self) -> list[str]:
        return sorted(git(self.target, "ls-files").split())

    def run_publish(self, **kw):
        return pub.publish(self.private, log=lambda *_: None, **kw)

    def test_publishes_the_listed_files_with_renames_and_nothing_else(self):
        self.repo(
            {"app/main.py": "x", "app/__pycache__/m.pyc": "c", "public/README.md": "public readme", "public/meta/m.json": "{}", "docs/notes.md": "private", "CLAUDE.md": "rules"},
            "target: ../proj\napp/**\nCLAUDE.md\npublic/README.md -> README.md\npublic/meta/** -> .meta/\n",
        )
        commit, target = self.run_publish()
        self.assertEqual(target, self.target.resolve())
        self.assertIn("Publish", commit)
        self.assertIn("first", commit)
        self.assertEqual(self.published(), [".meta/m.json", "CLAUDE.md", "README.md", "app/main.py"])
        # the same state publishes nothing new
        self.assertEqual(self.run_publish()[0], None)

    def test_a_file_dropped_from_the_list_leaves_the_public_tree(self):
        self.repo({"a.md": "a", "b.md": "b"}, "target: ../proj\na.md\nb.md\n")
        self.run_publish()
        write(self.private / "publish.txt", "target: ../proj\na.md\n")
        git(self.private, "commit", "-qam", "drop b")
        self.run_publish()
        self.assertEqual(self.published(), ["a.md"])

    def test_globs_hold_back_never_public_files(self):
        self.repo({"README.md": "r", "JOURNAL.md": "j", "CLAUDE.local.md": "l", "literature/bibliography.json": "[]", "literature/Smith_2020.md": "text"}, "target: ../proj\n*.md\nliterature/**\n")
        logs = []
        pub.publish(self.private, log=logs.append)
        self.assertEqual(self.published(), ["README.md", "literature/bibliography.json"])
        self.assertTrue(any("held back" in l and "JOURNAL.md" in l and "publish.txt" not in l for l in logs))

    def test_an_explicit_never_public_file_stops_the_publication(self):
        self.repo({"JOURNAL.md": "j"}, "target: ../proj\nJOURNAL.md\n")
        with self.assertRaises(pub.PublishError) as ctx:
            self.run_publish()
        self.assertIn("JOURNAL.md never goes public", str(ctx.exception))
        self.assertFalse(self.target.exists())

    def test_a_stale_rule_or_a_credential_stops_the_publication(self):
        self.repo({"a.md": "a", "cfg.py": f"KEY = '{FAKE_AWS}'"}, "target: ../proj\na.md\ngone/**\n")
        with self.assertRaises(pub.PublishError) as ctx:
            self.run_publish()
        self.assertIn("rule matches no committed file: gone/**", str(ctx.exception))
        write(self.private / "publish.txt", "target: ../proj\na.md\ncfg.py\n")
        git(self.private, "commit", "-qam", "fix")
        with self.assertRaises(pub.PublishError) as ctx:
            self.run_publish()
        self.assertIn("AWS access key in cfg.py", str(ctx.exception))
        self.assertNotIn(FAKE_AWS, str(ctx.exception))

    def test_only_committed_content_is_published(self):
        self.repo({"a.md": "committed"}, "target: ../proj\na.md\n")
        write(self.private / "a.md", "not yet committed")
        self.run_publish()
        self.assertEqual((self.target / "a.md").read_text(encoding="utf-8"), "committed")

    def test_check_mode_writes_nothing_and_commands_run(self):
        self.repo({"a.md": "a"}, f"target: ../proj\ncheck: {{python}} -c \"import sys; sys.exit(0)\"\na.md\n")
        self.assertEqual(self.run_publish(check_only=True)[0], None)
        self.assertFalse(self.target.exists())
        write(self.private / "publish.txt", "target: ../proj\ncheck: {python} -c \"import sys; sys.exit(3)\"\na.md\n")
        git(self.private, "commit", "-qam", "failing check")
        with self.assertRaises(pub.PublishError):
            self.run_publish()

    def test_validate_runs_on_the_written_tree_before_the_commit(self):
        self.repo({"a.md": "a"}, "target: ../proj\nvalidate: {python} -c \"import pathlib, sys; sys.exit(0 if pathlib.Path(sys.argv[1], 'a.md').exists() else 1)\" {target}\na.md\n")
        commit, _ = self.run_publish()
        self.assertIsNotNone(commit)

    def test_main_reports_findings_with_exit_code_1(self):
        self.repo({"a.md": "a"}, "target: ../proj\nmissing.md\n")
        with mock.patch("sys.stdout.reconfigure", create=True):
            self.assertEqual(pub.main(["--repo", str(self.private)]), 1)


if __name__ == "__main__":
    unittest.main()
