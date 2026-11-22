"""Tests for second_opinion.py. Run with: python -m unittest test_second_opinion.py (from this folder) or with pytest.

The real reviewer (Antigravity CLI) is never called: its command line is checked as a list, and the runs use
stand-in reviewers that are small Python programs started with the interpreter running the tests.
Every test works in a temporary folder; nothing outside it is read or written.
"""

import dataclasses
import datetime
import json
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import second_opinion as so  # noqa: E402

PY = sys.executable


def fake(name: str, code: str, *, status_code: str = "print('ok')", **kw) -> so.Reviewer:
    """A stand-in reviewer that runs `python -c code` with the message on stdin; its stdout is the answer."""
    return so.Reviewer(
        name=name,
        label=name,
        executable=PY,
        build=lambda exe, packet, answer, model, effort: [exe, "-c", code],
        stdin_format=lambda message: message,
        parse_stdout=lambda stdout: stdout,
        status=lambda exe: [exe, "-c", status_code],
        install="install it",
        **kw,
    )


class SecondOpinionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.run_dir = so.new_run(self.tmp, "Lettera alle società", now=datetime.datetime(2026, 10, 16, 9, 30, 0))
        (self.run_dir / "packet" / "prompt.md").write_text("Review the letter.", encoding="utf-8")
        (self.run_dir / "packet" / "files" / "letter.md").write_text("Gentili colleghi,", encoding="utf-8")

    def test_new_run_creates_the_layout_with_a_safe_name(self):
        self.assertEqual(self.run_dir.name, "20261016-093000-lettera-alle-societ")
        self.assertTrue((self.run_dir / "packet" / "files").is_dir())
        self.assertTrue((self.run_dir / "out").is_dir())
        self.assertEqual(so.new_run(self.tmp, "!!!").name.split("-", 2)[2], "review")

    def test_agy_reads_one_json_event_on_stdin_and_answers_in_the_result_event(self):
        argv = so.agy_command("agy", pathlib.Path("p"), pathlib.Path("o"), "gemini-4-neon-high", None)
        self.assertEqual(argv[:5], ["agy", "--input-format", "stream-json", "--output-format", "stream-json"])
        self.assertNotIn("-p", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "gemini-4-neon-high")
        self.assertNotIn("--effort", argv)
        self.assertEqual(so.REVIEWERS["gemini"].model, "gemini-4-neon-high")
        line = so.agy_stdin("Gentili colleghi,\nrighe à capo")
        self.assertTrue(line.endswith("\n") and line.count("\n") == 1)
        self.assertEqual(json.loads(line), {"event": "user", "message": {"content": "Gentili colleghi,\nrighe à capo"}})
        # The shape of a real run: init, step updates, then the result.
        stream = "\n".join([
            '{"event":"init","init":{"model":"gemini-4-neon-high"}}',
            '{"event":"step_update","step_update":{"text_delta":"banana"}}',
            '{"event":"result","result":{"status":"SUCCESS","response":"banana\\n"}}',
        ])
        self.assertEqual(so.agy_answer(stream), "banana\n")
        self.assertEqual(so.agy_answer(stream.replace("SUCCESS", "ERROR")), "")
        self.assertEqual(so.agy_answer("not json\n"), "")

    def test_the_message_holds_prompt_context_and_text_files_and_leaves_binaries_out(self):
        packet = self.run_dir / "packet"
        (packet / "context.md").write_text("Lettori: i colleghi.", encoding="utf-8")
        (packet / "files" / "deck.pptx").write_bytes(b"PK\x03\x04\xff\xfe binary")
        message, skipped = so.compose_message(packet)
        self.assertTrue(message.startswith(so.MESSAGE_HEADER))
        order = [message.index(f"===== {p} =====") for p in ("prompt.md", "context.md", "files/letter.md")]
        self.assertEqual(order, sorted(order))
        self.assertIn("Lettori: i colleghi.", message)
        self.assertIn("Gentili colleghi,", message)
        self.assertEqual(skipped, ["files/deck.pptx"])
        self.assertNotIn("deck.pptx", message)

    def test_a_file_beside_files_is_reported_as_not_sent(self):
        # On 22 November a packet kept global/ and conventions/ next to files/: they never reached the reviewer,
        # and the report said nothing was left out.
        packet = self.run_dir / "packet"
        (packet / "global").mkdir()
        (packet / "global" / "rules.md").write_text("Le regole globali.", encoding="utf-8")
        message, skipped = so.compose_message(packet)
        self.assertEqual(skipped, ["global/rules.md"])
        self.assertNotIn("Le regole globali.", message)

    def test_run_collects_the_answers_of_reviewers_in_parallel(self):
        reviewers = {
            # Prints the name of its working folder, which must be the packet.
            "a": fake("a", "import os, sys; sys.stdin.read(); print('answer from', os.path.basename(os.getcwd()))"),
            # Echoes what it read on stdin, which must be the composed message.
            "b": fake("b", "import sys; sys.stdout.write(sys.stdin.read())"),
        }
        report = so.run_all(self.run_dir, ["a", "b"], {}, {}, 60, reviewers)
        status = {r["reviewer"]: r["status"] for r in report["reviewers"]}
        self.assertEqual(status, {"a": "ok", "b": "ok"})
        out = self.run_dir / "out"
        self.assertEqual((out / "a.md").read_text(encoding="utf-8").strip(), "answer from packet")
        self.assertEqual((out / "b.md").read_text(encoding="utf-8").strip(), so.compose_message(self.run_dir / "packet")[0].strip())
        self.assertEqual(report["not_sent"], [])
        self.assertTrue((out / "a.log").is_file())
        saved = json.loads((out / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["packet_changes"], {"added": [], "changed": [], "removed": []})

    def test_a_reviewer_writing_into_the_packet_is_reported(self):
        reviewers = {"w": fake("w", "open('note.txt', 'w').write('x'); open('files/letter.md', 'a').write('!'); print('done')")}
        report = so.run_all(self.run_dir, ["w"], {}, {}, 60, reviewers)
        self.assertEqual(report["packet_changes"], {"added": ["note.txt"], "changed": ["files/letter.md"], "removed": []})

    def test_a_reviewer_past_its_timeout_is_stopped_and_reported(self):
        reviewers = {"slow": fake("slow", "import time; time.sleep(30)")}
        start = time.monotonic()
        report = so.run_all(self.run_dir, ["slow"], {}, {}, 1, reviewers)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual(report["reviewers"][0]["status"], "timeout")
        self.assertIsNone(report["reviewers"][0]["answer"])

    def test_failure_empty_answer_and_missing_tool_are_told_apart(self):
        missing = dataclasses.replace(fake("m", "print('x')"), executable="no-such-tool-for-second-opinion")
        reviewers = {
            "f": fake("f", "import sys; sys.stderr.write('boom'); sys.exit(2)"),
            "e": fake("e", "pass"),
            "m": missing,
        }
        # An answer left by an earlier run must not make the empty one look answered.
        (self.run_dir / "out" / "e.md").write_text("stale answer", encoding="utf-8")
        report = so.run_all(self.run_dir, ["f", "e", "m"], {}, {}, 60, reviewers)
        status = {r["reviewer"]: r["status"] for r in report["reviewers"]}
        self.assertEqual(status, {"f": "failed", "e": "empty", "m": "not installed"})
        self.assertIn("boom", (self.run_dir / "out" / "f.log").read_text(encoding="utf-8"))

    def test_models_and_efforts_override_the_defaults(self):
        seen = {}

        def build(exe, packet, answer, model, effort):
            seen.update(model=model, effort=effort)
            return [exe, "-c", "print('ok')"]

        rev = dataclasses.replace(fake("x", ""), build=build, model="default-model", effort="high")
        so.run_all(self.run_dir, ["x"], {"x": "other-model"}, {}, 60, {"x": rev})
        self.assertEqual(seen, {"model": "other-model", "effort": "high"})

    def test_run_needs_a_prompt(self):
        (self.run_dir / "packet" / "prompt.md").unlink()
        with self.assertRaises(SystemExit):
            so.run_all(self.run_dir, ["a"], {}, {}, 60, {"a": fake("a", "print('x')")})

    def test_dry_run_prints_the_commands_and_writes_nothing(self):
        lines = so.dry_run(self.run_dir, ["gemini"], {}, {})
        self.assertTrue(lines[0].startswith("gemini: ") and "stream-json" in lines[0] and lines[0].endswith("stdin"))
        self.assertIn(so.REVIEWERS["gemini"].model, lines[0])
        self.assertEqual(list((self.run_dir / "out").iterdir()), [])

    def test_check_reports_ready_not_signed_in_and_not_installed(self):
        reviewers = {
            # As `agy models` prints them: slug, tab, display name.
            "r": fake("r", "", status_code="print('gemini-4-argon-high\\tGemini 4 Argon (High)\\ngemini-3.1-pro-high\\tGemini 3.1 Pro (High)')", model="gemini-4-argon-high", status_lists_models=True),
            "nomodel": fake("nomodel", "", status_code="print('gemini-3.8-flash-high\\tGemini 3.8 Flash (High)')", model="gemini-4-argon-high", status_lists_models=True),
            "out": fake("out", "", status_code="import sys; print('Not logged in'); sys.exit(1)"),
            "none": dataclasses.replace(fake("none", ""), executable="no-such-tool-for-second-opinion"),
        }
        results = {r["reviewer"]: r for r in so.check(list(reviewers), reviewers)}
        self.assertEqual(results["r"]["status"], "ready")
        self.assertEqual(results["r"]["detail"], "models: gemini-4-argon-high, gemini-3.1-pro-high")
        self.assertEqual(results["nomodel"]["status"], "ready")
        self.assertIn("not listed", results["nomodel"]["detail"])
        self.assertIn("models: gemini-3.8-flash-high", results["nomodel"]["detail"])
        self.assertEqual(results["out"]["status"], "not signed in")
        self.assertIn("Not logged in", results["out"]["detail"])
        self.assertEqual(results["none"]["status"], "not installed")

    def test_command_line_options_are_validated(self):
        self.assertEqual(so.pairs(["gemini=gemini-4-neon-xhigh"], so.REVIEWERS), {"gemini": "gemini-4-neon-xhigh"})
        self.assertEqual(so.names_arg(" gemini ", so.REVIEWERS), ["gemini"])
        # Naming a reviewer that does not exist is an error, never a silent skip.
        for bad in (lambda: so.pairs(["gpt=x"], so.REVIEWERS), lambda: so.pairs(["gemini"], so.REVIEWERS), lambda: so.names_arg("gemini,gpt", so.REVIEWERS)):
            with self.assertRaises(SystemExit):
                bad()

    def test_export_writes_the_same_message_a_run_sends(self):
        (self.run_dir / "packet" / "files" / "scan.pdf").write_bytes(b"\xff\xfe\x00binary")
        target, skipped = so.export_packet(self.run_dir)
        self.assertEqual(target, self.run_dir / "out" / "packet-to-paste.md")
        # the file is the message of compose_message, so a web app reads what the command-line reviewers read
        self.assertEqual(target.read_text(encoding="utf-8"), so.compose_message(self.run_dir / "packet")[0])
        self.assertIn("Gentili colleghi,", target.read_text(encoding="utf-8"))
        self.assertEqual(skipped, ["files/scan.pdf"])
        self.assertEqual(so.main(["export", str(self.run_dir)]), 0)

    def test_export_needs_a_packet(self):
        (self.run_dir / "packet" / "prompt.md").unlink()
        with self.assertRaises(SystemExit):
            so.export_packet(self.run_dir)

    def test_import_saves_a_reply_and_refuses_a_fragment(self):
        reply = self.tmp / "pasted.txt"
        reply.write_text("  " + "Una stesura alternativa della lettera. " * 10 + "\n\n", encoding="utf-8")
        target = so.import_answer(self.run_dir, "Gemini web", reply)
        self.assertEqual(target, self.run_dir / "out" / "gemini-web.md")
        self.assertTrue(target.read_text(encoding="utf-8").startswith("Una stesura alternativa"))
        # the failure this guards against: a copy that caught one word of the answer
        reply.write_text("Certamente!", encoding="utf-8")
        with self.assertRaises(SystemExit):
            so.import_answer(self.run_dir, "argon", reply)
        self.assertFalse((self.run_dir / "out" / "argon.md").exists())
        with self.assertRaises(SystemExit):
            so.import_answer(self.run_dir, "???", reply)


if __name__ == "__main__":
    unittest.main()
