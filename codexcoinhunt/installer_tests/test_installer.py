"""Copy-integrity checks, separate from the 107 research engineering checks."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_codexcoinhunt as installer


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.destination = self.root / "Projects" / "CodexCoinHunt"

    def tearDown(self):
        self.temporary.cleanup()

    def archive(self, name="copy.zip", text="first", extra=None, corrupt=False):
        data = {"README.md": text.encode(), ".ai/CLAUDE_NOTES.md": b"unreviewed\n"}
        manifest = {"format_version": 1, "project_id": installer.PROJECT_ID,
                    "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "files": [{"file": path, "bytes": len(body),
                               "sha256": hashlib.sha256(body).hexdigest()}
                              for path, body in sorted(data.items())]}
        archive = self.root / name
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr(installer.PREFIX + "PROJECT_MANIFEST.json", json.dumps(manifest))
            for path, body in data.items():
                output.writestr(installer.PREFIX + path,
                                b"changed" if corrupt and path == "README.md" else body)
            if extra:
                output.writestr(*extra)
        return archive

    def test_fresh_copy_preserves_existing_root_claude_files(self):
        self.destination.mkdir(parents=True)
        existing = self.destination / "CLAUDE.md"
        existing.write_text("real user notes")
        result = installer.install(self.archive(), self.destination)
        self.assertEqual(existing.read_text(), "real user notes")
        self.assertEqual(result["files_verified"], 2)
        self.assertEqual(Path(result["installed_path"]).joinpath("README.md").read_text(), "first")
        self.assertTrue(json.loads(Path(result["installed_path"]).joinpath("ORIGIN.json").read_text())["copy_only"])

    def test_update_archives_existing_managed_edits(self):
        first = installer.install(self.archive(), self.destination)
        current = Path(first["installed_path"])
        (current / "user_edit.txt").write_text("preserve my edit")
        second = installer.install(self.archive("second.zip", "second"), self.destination)
        self.assertEqual(current.joinpath("README.md").read_text(), "second")
        previous = Path(second["previous_snapshot"])
        self.assertEqual(previous.joinpath("README.md").read_text(), "first")
        self.assertEqual(previous.joinpath("user_edit.txt").read_text(), "preserve my edit")

    def test_unrecognized_current_is_preserved(self):
        current = self.destination / "codex-research" / "current"
        current.mkdir(parents=True)
        current.joinpath("CLAUDE.md").write_text("unrecognized work")
        result = installer.install(self.archive(), self.destination)
        self.assertEqual(result["status"], "copied_existing_current_preserved")
        self.assertEqual(current.joinpath("CLAUDE.md").read_text(), "unrecognized work")
        self.assertEqual(Path(result["installed_path"]).parent.name, "imports")
        self.assertEqual(Path(result["installed_path"]).joinpath("README.md").read_text(), "first")

    def test_corrupt_hash_is_rejected_before_destination_creation(self):
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            installer.install(self.archive(corrupt=True), self.destination)
        self.assertFalse(self.destination.exists())

    def test_unlisted_member_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "membership differ"):
            installer.install(self.archive(extra=(installer.PREFIX + "unlisted", b"extra")), self.destination)
        self.assertFalse(self.destination.exists())

    def test_parent_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsafe archive path"):
            installer.install(self.archive(extra=(installer.PREFIX + "../outside", b"bad")), self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.root / "outside").exists())

    def test_archive_symlink_is_rejected(self):
        info = zipfile.ZipInfo(installer.PREFIX + "link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(ValueError, "symbolic-link"):
            installer.install(self.archive(extra=(info, b"/outside")), self.destination)
        self.assertFalse(self.destination.exists())

    def test_existing_current_symlink_is_untouched(self):
        outside = self.root / "outside"
        outside.mkdir()
        outside.joinpath("CLAUDE.md").write_text("outside notes")
        managed = self.destination / "codex-research"
        managed.mkdir(parents=True)
        current = managed / "current"
        current.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            installer.install(self.archive(), self.destination)
        self.assertTrue(current.is_symlink())
        self.assertEqual(outside.joinpath("CLAUDE.md").read_text(), "outside notes")

    def test_failed_current_switch_restores_previous_snapshot(self):
        first = installer.install(self.archive(), self.destination)
        current = Path(first["installed_path"])
        next_archive = self.archive("second.zip", "second")
        real_rename = Path.rename
        def fail_switch(path, target):
            if path.name.startswith("incoming-") and Path(target) == current:
                raise OSError("synthetic switch failure")
            return real_rename(path, target)
        with patch.object(Path, "rename", fail_switch):
            with self.assertRaisesRegex(OSError, "synthetic switch failure"):
                installer.install(next_archive, self.destination)
        self.assertEqual(current.joinpath("README.md").read_text(), "first")
        self.assertEqual(list(current.parent.glob("incoming-*")), [])


if __name__ == "__main__":
    unittest.main()
