from __future__ import annotations

import hashlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compile_resume import (  # noqa: E402
    ASSETS,
    CompileError,
    asset_for_platform,
    compile_resume,
    ensure_tectonic,
    extract_binary,
    overfull_boxes,
    pages_from_log,
    pages_from_pdf,
    verify_sha256,
)


EXAMPLE_TEX = ROOT / "examples" / "output" / "tailored-resume-example-company-example-city.tex"
LOG_TEXT = """This is XeTeX, Version 3.141592653
Overfull \\hbox (4.2pt too wide) in paragraph at lines 40--42
! Undefined control sequence.
l.47 \\textbff
Output written on resume.xdv (2 pages, 9876 bytes).
"""
# A stand-in for Tectonic: writes a PDF and log, or fails like a LaTeX error.
FAKE_TECTONIC = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
outdir = Path(args[args.index("--outdir") + 1])
tex = Path(args[-1])
if "fail" in tex.read_text():
    print("error: " + tex.name + ":5: Undefined control sequence")
    sys.exit(1)
(outdir / (tex.stem + ".pdf")).write_bytes(b"%PDF-1.5\\n<< /Type /Pages /Count 2 >>\\n")
(outdir / (tex.stem + ".log")).write_text({log!r})
"""


def _tar_archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _zip_archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class TectonicInstallTests(unittest.TestCase):
    def test_platforms_map_to_pinned_assets(self) -> None:
        cases = {
            ("Linux", "x86_64"): "x86_64-unknown-linux-musl.tar.gz",
            ("Linux", "aarch64"): "aarch64-unknown-linux-musl.tar.gz",
            ("Darwin", "x86_64"): "x86_64-apple-darwin.tar.gz",
            ("Darwin", "arm64"): "aarch64-apple-darwin.tar.gz",
            ("Windows", "AMD64"): "x86_64-pc-windows-msvc.zip",
            ("Windows", "ARM64"): "x86_64-pc-windows-msvc.zip",
        }
        for (system, machine), asset in cases.items():
            with self.subTest(system=system, machine=machine):
                self.assertEqual(asset_for_platform(system, machine), asset)
                self.assertIn(asset, ASSETS)

    def test_unsupported_platform_is_rejected(self) -> None:
        with self.assertRaises(CompileError):
            asset_for_platform("FreeBSD", "x86_64")

    def test_checksum_mismatch_is_rejected(self) -> None:
        data = b"tampered archive"
        verify_sha256(data, hashlib.sha256(data).hexdigest())
        with self.assertRaises(CompileError):
            verify_sha256(data, "0" * 64)

    def test_binary_is_extracted_from_tar_and_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            extract_binary(_tar_archive({"tectonic": b"unix"}), "x86_64-apple-darwin.tar.gz", root / "tectonic")
            extract_binary(_zip_archive({"tectonic.exe": b"windows"}), "x86_64-pc-windows-msvc.zip", root / "tectonic.exe")
            self.assertEqual((root / "tectonic").read_bytes(), b"unix")
            self.assertEqual((root / "tectonic.exe").read_bytes(), b"windows")
            if os.name != "nt":
                self.assertTrue(os.access(root / "tectonic", os.X_OK))

    def test_unexpected_archive_contents_are_rejected(self) -> None:
        for members in (
            {"../tectonic": b"escape"},
            {"bin/tectonic": b"nested"},
            {"tectonic": b"binary", "extra": b"surprise"},
        ):
            with self.subTest(members=list(members)):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    with self.assertRaises(CompileError):
                        extract_binary(
                            _tar_archive(members),
                            "x86_64-unknown-linux-musl.tar.gz",
                            Path(temporary_directory) / "tectonic",
                        )

    def test_existing_installation_is_reused_without_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            tools_dir = Path(temporary_directory)
            binary = tools_dir / "tectonic-0.17.0" / (
                "tectonic.exe" if os.name == "nt" else "tectonic"
            )
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"already installed")
            self.assertEqual(ensure_tectonic(tools_dir), binary)


class OutputInspectionTests(unittest.TestCase):
    def test_page_count_is_read_from_log(self) -> None:
        self.assertEqual(pages_from_log(LOG_TEXT), 2)
        self.assertEqual(pages_from_log("Output written on a.xdv (1 page, 10 bytes)."), 1)
        self.assertIsNone(pages_from_log("no output"))

    def test_overfull_boxes_are_read_from_log_and_console(self) -> None:
        console = "warning: resume.tex:40: Overfull \\hbox (4.2pt too wide) in paragraph at lines 40--42"
        self.assertEqual(
            overfull_boxes(LOG_TEXT + "\n" + console),
            ["Overfull \\hbox (4.2pt too wide) in paragraph at lines 40--42"],
        )

    def test_page_count_is_read_from_plain_and_compressed_pdf(self) -> None:
        plain = b"%PDF-1.4\n<< /Type /Outlines /Count 7 >>\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n"
        self.assertEqual(pages_from_pdf(plain), 1)
        compressed = zlib.compress(b"<< /Count 3 /Kids [4 0 R 5 0 R 6 0 R] /Type /Pages >>")
        stream = b"%PDF-1.5\n1 0 obj\n<< /Type /ObjStm >>\nstream\n" + compressed + b"\nendstream\n"
        self.assertEqual(pages_from_pdf(stream), 3)
        self.assertIsNone(pages_from_pdf(b"%PDF-1.5\n"))


@unittest.skipIf(os.name == "nt", "the fake Tectonic is a POSIX script")
class CompileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        self.tectonic = self.root / "tectonic"
        self.tectonic.write_text(FAKE_TECTONIC.format(python=sys.executable, log=LOG_TEXT))
        self.tectonic.chmod(0o755)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _compile(self, content: str, max_pages: int = 1):
        tex = self.root / "resume.tex"
        tex.write_text(content)
        return compile_resume(tex, self.tectonic, self.root / "pdf", max_pages, cache_dir=None)

    def test_successful_compile_reports_pages_and_layout_warnings(self) -> None:
        result = self._compile("\\documentclass{article}")
        self.assertTrue(result.is_valid, result.errors)
        self.assertEqual(result.pages, 2)
        self.assertTrue(any("more than the limit of 1" in warning for warning in result.warnings))
        self.assertTrue(any("Overfull \\hbox" in warning for warning in result.warnings))

    def test_page_limit_can_be_raised(self) -> None:
        result = self._compile("\\documentclass{article}", max_pages=2)
        self.assertFalse(any("more than the limit" in warning for warning in result.warnings))

    def test_failed_compile_reports_errors(self) -> None:
        result = self._compile("fail")
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Undefined control sequence" in error for error in result.errors))


@unittest.skipUnless(
    os.environ.get("TAILORED_RESUME_KIT_COMPILE_TEST") == "1",
    "set TAILORED_RESUME_KIT_COMPILE_TEST=1 to download Tectonic and compile the example",
)
class ExampleCompileTests(unittest.TestCase):
    def test_example_resume_compiles_to_one_page(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = compile_resume(EXAMPLE_TEX, ensure_tectonic(), Path(temporary_directory), 1)
        self.assertTrue(result.is_valid, result.errors)
        self.assertEqual(result.pages, 1)


if __name__ == "__main__":
    unittest.main()
