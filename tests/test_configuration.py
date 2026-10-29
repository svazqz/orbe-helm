"""User defaults and remote skill tests use isolated homes and mocked public sources."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from orbehelm.cli import main
from orbehelm.configuration import load
from orbehelm.core import OrbeHelmError, build, resolve
from orbehelm.remote_skills import archive_files, download, fetch, MAX_DOWNLOAD

REPO = Path(__file__).resolve().parents[1]
SKILL = b"---\nname: laravel-specialist\ndescription: Laravel application development.\n---\n# Laravel\nUse references/models.md.\n"
URL = "https://github.com/example/skills/tree/main/skills/laravel"


def archive(entries=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for name, data in (entries or {
            "repository-main/skills/laravel/SKILL.md": SKILL,
            "repository-main/skills/laravel/references/models.md": b"Model reference.",
            "repository-main/unrelated.txt": b"Do not install this.",
        }).items():
            package.writestr(name, data)
    return buffer.getvalue()


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=REPO / "tests")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("definitions", "registry", "examples"):
            shutil.copytree(REPO / name, self.root / name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()
        self.rc = self.home / ".orbehelmrc"
        self.environment = patch.dict(os.environ, {"HOME": str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("ORBEHELM_CONFIG", None)
        os.environ.pop("ORBEHELM_ROOT", None)
        download.cache_clear()
        self.addCleanup(download.cache_clear)

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--root", str(self.root), "--project", str(self.project), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def snapshot(self):
        return {str(path.relative_to(self.root)): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                for path in [self.root, *self.root.rglob("*")]}

    def test_missing_default_config_is_optional_and_read_only(self):
        before = self.snapshot()
        self.assertEqual(load(), ({}, {}))
        self.assertEqual(before, self.snapshot())
        with self.assertRaisesRegex(OrbeHelmError, "does not exist"):
            load(self.home / "missing.ini")

    def test_home_defaults_cli_precedence_and_empty_selection_override(self):
        self.rc.write_text("[ORBEHELM]\nagent=claude\nprofile=developer\nspec=php\nskills=testing\nskillsets=quality\nstrict=false\n")
        code, output, _ = self.cli("resolve")
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["spec"], "php")
        self.assertEqual(data["selected_skills"], ["testing"])
        self.assertEqual([item["name"] for item in data["skills"]], ["testing", "review"])
        code, output, _ = self.cli("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("claude --append-system-prompt-file", output)
        code, output, _ = self.cli("resolve", "--spec=rust", "--skills=", "--skillset=")
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["spec"], "rust")
        self.assertEqual(data["skills"], [])
        code, output, _ = self.cli("--dry-run", "--agent=codex")
        self.assertEqual(code, 0)
        self.assertIn("codex --no-daemon", output)

    def test_relative_paths_custom_config_and_environment_precedence(self):
        self.rc.write_text("[orbehelm]\nroot=..\nproject=../project\n[skills]\nlocal=../examples/skills/testing\n")
        defaults, mappings = load()
        self.assertEqual(defaults["root"], self.root)
        self.assertEqual(defaults["project"], self.project)
        self.assertEqual(mappings["local"], str(self.root / "examples/skills/testing"))
        other = self.home / "other.ini"
        other.write_text("[ORBEHELM]\nagent=opencode\n")
        with patch.dict(os.environ, {"ORBEHELM_CONFIG": str(other)}):
            self.assertEqual(load()[0]["agent"], "opencode")
            self.assertIn("local", load(self.rc)[1])
        with patch.dict(os.environ, {"ORBEHELM_ROOT": str(self.root)}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["resolve", "--project", str(self.project)]), 0)
            self.assertEqual(json.loads(output.getvalue())["root"], str(self.root))

    def test_invalid_configuration_is_rejected(self):
        cases = ["[UNKNOWN]\nx=y", "[DEFAULT]\nagent=codex", "[ORBEHELM]\nunknown=true",
                 "[ORBEHELM]\nagent=wrong", "[ORBEHELM]\nstrict=maybe", "[ORBEHELM]\nskills=testing,,review",
                 "[SKILLS]\nbad_name=https://example.com/SKILL.md", "[SKILLS]\nx=",
                 "[SKILLS]\nx=http://example.com/SKILL.md", "[SKILLS]\nx=https://user:secret@example.com/SKILL.md",
                 "[ORBEHELM]\nagent=codex\nagent=claude", "[SKILLS]\nx=https://example.com/SKILL.md#invalid",
                 "[SKILLS]\nx=https://example.com/a\n[skills]\ny=https://example.com/b"]
        for text in cases:
            with self.subTest(text=text):
                self.rc.write_text(text)
                with self.assertRaises(OrbeHelmError):
                    load()

    def test_strict_default_can_be_overridden_explicitly(self):
        self.rc.write_text("[ORBEHELM]\nstrict=true\n")
        self.assertEqual(self.cli("--dry-run")[0], 2)
        self.assertEqual(self.cli("--dry-run", "--no-strict")[0], 0)

    def test_local_alias_direct_selection_and_listing(self):
        self.rc.write_text("[SKILLS]\ncustom=../examples/skills/testing\n")
        code, output, _ = self.cli("resolve", "--skills=custom,custom,review")
        self.assertEqual(code, 0)
        self.assertEqual([item["name"] for item in json.loads(output)["skills"]], ["custom", "review"])
        code, output, _ = self.cli("skills", "list")
        self.assertEqual(code, 0)
        self.assertIn("custom", json.loads(output)["available"])

    def test_remote_build_installs_references_and_reuses_offline_cache(self):
        self.rc.write_text(f"[SKILLS]\nlaravel={URL}\n")
        with patch("orbehelm.remote_skills.fetch", return_value=archive()) as network:
            code, output, error = self.cli("build", "--spec=php", "--skills=laravel")
        self.assertEqual((code, error), (0, ""))
        network.assert_called_once()
        result = json.loads(output)
        target = Path(result["output"])
        self.assertEqual((target / "skills/laravel/references/models.md").read_text(), "Model reference.")
        self.assertFalse((target / "skills/laravel/unrelated.txt").exists())
        self.assertIn("# Laravel", (target / "instructions.md").read_text())
        download.cache_clear()
        before = (target / "instructions.md").stat().st_mtime_ns
        with patch("orbehelm.remote_skills.fetch", side_effect=AssertionError("unexpected network")):
            code, output, error = self.cli("build", "--spec=php", "--skills=laravel")
        self.assertEqual((code, error), (0, ""))
        self.assertTrue(json.loads(output)["cached"])
        self.assertEqual(json.loads(output)["output"], str(target))
        self.assertEqual((target / "instructions.md").stat().st_mtime_ns, before)
        before = self.snapshot()
        with patch("orbehelm.remote_skills.fetch", side_effect=AssertionError("unexpected network")):
            self.assertEqual(self.cli("--dry-run", "--spec=php", "--skills=laravel")[0], 0)
        self.assertEqual(before, self.snapshot())

    def test_cold_remote_dry_run_writes_nothing_and_predicts_build_hash(self):
        self.rc.write_text(f"[ORBEHELM]\nspec=php\nskills=laravel\n[SKILLS]\nlaravel={URL}\n")
        before = self.snapshot()
        with patch("orbehelm.remote_skills.fetch", return_value=archive()):
            code, command, error = self.cli("--dry-run")
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(before, self.snapshot())
            self.assertFalse((self.root / "state").exists())
            self.assertFalse((self.root / "generated").exists())
            code, output, error = self.cli("build")
        self.assertEqual((code, error), (0, ""))
        self.assertIn(json.loads(output)["output"], command)

    def test_manual_mapped_install_and_corrupted_cache_repair(self):
        self.rc.write_text(f"[SKILLS]\nlaravel={URL}\n")
        with patch("orbehelm.remote_skills.fetch", return_value=archive()):
            code, output, error = self.cli("skills", "install", "laravel")
            self.assertEqual((code, error), (0, ""))
            target = Path(json.loads(output)["installed"])
            (target / "SKILL.md").write_text("corrupted")
            self.assertEqual(self.cli("build", "--skills=laravel")[0], 0)
            self.assertEqual((target / "SKILL.md").read_bytes(), SKILL)

    def test_direct_skill_keeps_registered_transitive_dependencies(self):
        path = self.root / "registry/skills/review.json"
        data = json.loads(path.read_text())
        data["skills"] = ["testing"]
        path.write_text(json.dumps(data))
        result = resolve(self.root, project=self.project, skills=["review", "testing"])
        self.assertEqual([item["name"] for item in result["skills"]], ["testing", "review"])

    def test_standalone_https_skill_and_pins(self):
        with patch("orbehelm.remote_skills.fetch", return_value=SKILL):
            files, _, sha = download("https://example.com/SKILL.md")
            self.assertEqual(list(files), ["SKILL.md"])
            self.assertEqual(download("https://example.com/SKILL.md#sha256=" + sha)[2], sha)
            with self.assertRaisesRegex(OrbeHelmError, "pinned"):
                download("https://example.com/SKILL.md#sha256=" + "0" * 64)

    def test_invalid_remote_definitions_fail_without_installing(self):
        for payload in (b"<html>Not a skill</html>", b"---\nname: missing-description\n---\nBody", b"\xff"):
            download.cache_clear()
            with self.subTest(payload=payload), patch("orbehelm.remote_skills.fetch", return_value=payload):
                with self.assertRaises(OrbeHelmError):
                    download("https://example.com/SKILL.md")
        self.assertFalse((self.root / "state").exists())

    def test_unsafe_archives_are_rejected(self):
        base = "repository-main/skills/laravel/"
        for relative in ("../../escape", "/absolute", "bad\\path"):
            with self.subTest(relative=relative), self.assertRaises(OrbeHelmError):
                archive_files(archive({base + relative: b"bad"}), "skills/laravel")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            entry = zipfile.ZipInfo(base + "link")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            package.writestr(entry, "../../elsewhere")
        with self.assertRaisesRegex(OrbeHelmError, "Unsafe"):
            archive_files(buffer.getvalue(), "skills/laravel")
        with self.assertRaisesRegex(OrbeHelmError, "Invalid"):
            archive_files(b"not a zip", "skills/laravel")

    def test_download_response_limit(self):
        with patch("orbehelm.remote_skills.urlopen") as open_url:
            response = open_url.return_value.__enter__.return_value
            response.geturl.return_value = "https://example.com/SKILL.md"
            response.read.return_value = b"x" * (MAX_DOWNLOAD + 1)
            with self.assertRaisesRegex(OrbeHelmError, "32 MiB"):
                fetch("https://example.com/SKILL.md")


if __name__ == "__main__":
    unittest.main()
