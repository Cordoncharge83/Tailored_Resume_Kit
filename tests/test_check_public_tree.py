from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_public_tree import check_paths, check_repository  # noqa: E402


class PublicTreeTests(unittest.TestCase):
    def test_current_publishable_tree_is_safe(self) -> None:
        errors, file_count = check_repository(ROOT)
        self.assertFalse(errors, errors)
        self.assertGreater(file_count, 0)

    def test_private_working_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "candidate" / "profile.yaml"
            path.parent.mkdir(parents=True)
            path.write_text("profile: {}\n", encoding="utf-8")
            errors = check_paths(root, ["candidate/profile.yaml"])
        self.assertTrue(any("private working path" in error for error in errors))

    def test_high_confidence_secret_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "note.txt"
            secret = "-----BEGIN " + "PRIVATE KEY-----"
            path.write_text(secret, encoding="utf-8")
            errors = check_paths(root, ["note.txt"])
        self.assertTrue(any("private key" in error for error in errors))

    def test_non_example_email_is_rejected_from_examples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "examples" / "candidate" / "profile.yaml"
            path.parent.mkdir(parents=True)
            path.write_text("email: person@real.invalid\n", encoding="utf-8")
            errors = check_paths(root, ["examples/candidate/profile.yaml"])
        self.assertTrue(any("non-example email domain" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
