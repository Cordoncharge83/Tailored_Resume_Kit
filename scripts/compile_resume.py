#!/usr/bin/env python3
"""Optionally compile a tailored resume to PDF locally with a pinned Tectonic."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path


TECTONIC_VERSION = "0.17.0"
DOWNLOAD_URL = (
    "https://github.com/tectonic-typesetting/tectonic/releases/download/"
    "tectonic%40{version}/tectonic-{version}-{target}"
)
# SHA-256 digests of the official release archives. A download that does not
# match is never unpacked or run.
ASSETS = {
    "x86_64-unknown-linux-musl.tar.gz": "8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7",
    "aarch64-unknown-linux-musl.tar.gz": "b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8",
    "x86_64-apple-darwin.tar.gz": "7c90ef5b6ddb1eb1937e4337add5237b79338e4b9676459fa91187d24d6cdf80",
    "aarch64-apple-darwin.tar.gz": "a3f1cac7c5678f01661a92212f58480ae3b0634115d880dbc59e2953ded45667",
    "x86_64-pc-windows-msvc.zip": "f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f",
}
ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / ".tools"
DOWNLOAD_TIMEOUT_SECONDS = 120
COMPILE_TIMEOUT_SECONDS = 300

LOG_PAGES_PATTERN = re.compile(r"Output written on .*?\((\d+) pages?\b")
PDF_PAGES_PATTERN = re.compile(
    rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)|/Count\s+(\d+)[^>]*?/Type\s*/Pages\b"
)
PDF_STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
LOG_ERROR_PATTERN = re.compile(r"^! .*$|^l\.\d+ .*$", re.M)
OVERFULL_PATTERN = re.compile(r"Overfull \\hbox .*$", re.M)
# Backtrace and status lines Tectonic prints when it crashes.
NOISE_PATTERN = re.compile(r"^(?:\d+:|at |stack backtrace|note:|thread '.*' .*panicked)", re.I)
NETWORK_FAILURE_MARKERS = ("couldn't get it from the internet", "error sending request")


class CompileError(Exception):
    """Raised when Tectonic cannot be prepared or the resume cannot be compiled."""


@dataclass
class CompileResult:
    pdf_path: Path | None = None
    pages: int | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.pdf_path is not None and not self.errors


# Tectonic installation


def asset_for_platform(system: str | None = None, machine: str | None = None) -> str:
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    is_x86_64 = machine in {"x86_64", "amd64"}
    is_arm64 = machine in {"aarch64", "arm64"}
    if system == "linux" and is_x86_64:
        return "x86_64-unknown-linux-musl.tar.gz"
    if system == "linux" and is_arm64:
        return "aarch64-unknown-linux-musl.tar.gz"
    if system == "darwin" and is_x86_64:
        return "x86_64-apple-darwin.tar.gz"
    if system == "darwin" and is_arm64:
        return "aarch64-apple-darwin.tar.gz"
    # Windows on ARM runs the x86_64 build through emulation.
    if system == "windows" and (is_x86_64 or is_arm64):
        return "x86_64-pc-windows-msvc.zip"
    raise CompileError(
        f"no Tectonic {TECTONIC_VERSION} download for {system} {machine}; "
        "install Tectonic yourself and pass --tectonic"
    )


def _binary_name(asset: str) -> str:
    return "tectonic.exe" if asset.endswith(".zip") else "tectonic"


def installed_binary(asset: str, tools_dir: Path = TOOLS_DIR) -> Path:
    return tools_dir / f"tectonic-{TECTONIC_VERSION}" / _binary_name(asset)


def verify_sha256(data: bytes, expected: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise CompileError(
            f"downloaded Tectonic archive has SHA-256 {actual}, expected {expected}; "
            "refusing to use it"
        )


def extract_binary(archive: bytes, asset: str, destination: Path) -> None:
    """Extract only the top-level Tectonic executable from a release archive."""
    name = _binary_name(asset)
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = [info for info in bundle.infolist() if not info.is_dir()]
            if [info.filename for info in members] != [name]:
                raise CompileError(f"unexpected archive contents; expected only {name}")
            data = bundle.read(members[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            members = bundle.getmembers()
            if len(members) != 1 or members[0].name != name or not members[0].isfile():
                raise CompileError(f"unexpected archive contents; expected only {name}")
            extracted = bundle.extractfile(members[0])
            if extracted is None:
                raise CompileError(f"could not read {name} from the archive")
            data = extracted.read()

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    temporary.chmod(0o755)
    os.replace(temporary, destination)


def _download(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise CompileError(
            f"could not download Tectonic from {url} ({exc}); check the internet "
            "connection or pass --tectonic"
        ) from exc


def ensure_tectonic(tools_dir: Path = TOOLS_DIR) -> Path:
    asset = asset_for_platform()
    binary = installed_binary(asset, tools_dir)
    if binary.is_file():
        return binary
    url = DOWNLOAD_URL.format(version=TECTONIC_VERSION, target=asset)
    print(f"Downloading Tectonic {TECTONIC_VERSION} from {url}", file=sys.stderr)
    archive = _download(url)
    verify_sha256(archive, ASSETS[asset])
    extract_binary(archive, asset, binary)
    return binary


# Log and PDF inspection


def pages_from_log(log_text: str) -> int | None:
    match = LOG_PAGES_PATTERN.search(log_text)
    return int(match.group(1)) if match else None


def pages_from_pdf(pdf: bytes) -> int | None:
    """Read the page count from the PDF page tree, including compressed objects."""
    chunks = [pdf]
    for stream in PDF_STREAM_PATTERN.finditer(pdf):
        try:
            chunks.append(zlib.decompress(stream.group(1)))
        except zlib.error:
            continue
    counts = [
        int(match.group(1) or match.group(2))
        for chunk in chunks
        for match in PDF_PAGES_PATTERN.finditer(chunk)
    ]
    return max(counts) if counts else None


def errors_from_log(log_text: str) -> list[str]:
    return [line.strip() for line in LOG_ERROR_PATTERN.findall(log_text)]


def overfull_boxes(text: str) -> list[str]:
    """Return unique overfull-box warnings from a log or Tectonic's console output."""
    return list(dict.fromkeys(line.strip() for line in OVERFULL_PATTERN.findall(text)))


# Compilation


def compile_resume(
    tex_path: Path,
    tectonic: Path,
    outdir: Path,
    max_pages: int,
    cache_dir: Path | None = TOOLS_DIR / "tectonic-cache",
) -> CompileResult:
    result = CompileResult()
    outdir.mkdir(parents=True, exist_ok=True)
    pdf_path = outdir / f"{tex_path.stem}.pdf"
    log_path = outdir / f"{tex_path.stem}.log"
    for stale in (pdf_path, log_path):
        stale.unlink(missing_ok=True)

    environment = dict(os.environ)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        environment["TECTONIC_CACHE_DIR"] = str(cache_dir)
    command = [
        str(tectonic),
        "-X",
        "compile",
        "--untrusted",
        "--keep-logs",
        "--outdir",
        str(outdir),
        str(tex_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=environment,
            timeout=COMPILE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CompileError(f"could not run Tectonic ({exc.__class__.__name__}: {exc})") from exc

    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    if completed.returncode != 0 or not pdf_path.is_file():
        output = [line.strip() for line in (completed.stdout + completed.stderr).splitlines()]
        result.errors = [line for line in output if line.startswith("error:")]
        result.errors += errors_from_log(log_text)
        if not result.errors:
            result.errors = [line for line in output if line and not NOISE_PATTERN.match(line)][-10:]
        if any(marker in line for line in output for marker in NETWORK_FAILURE_MARKERS):
            result.errors.insert(
                0,
                "Tectonic could not download the LaTeX packages it needs; the first "
                "compile needs internet access, after which packages are cached",
            )
        if not result.errors:
            result.errors = [f"Tectonic exited with status {completed.returncode}"]
        return result

    result.pdf_path = pdf_path
    result.pages = pages_from_log(log_text) or pages_from_pdf(pdf_path.read_bytes())
    if result.pages is None:
        result.warnings.append("could not determine the page count")
    elif result.pages > max_pages:
        result.warnings.append(
            f"{result.pages} pages, more than the limit of {max_pages}; omit lower-relevance "
            "content rather than shrinking fonts, margins, or spacing"
        )
    for line in overfull_boxes(log_text + "\n" + completed.stdout + completed.stderr):
        result.warnings.append(f"text runs into the margin: {line}")
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compile a tailored resume to PDF with a pinned, checksum-verified Tectonic. "
            "The first run downloads Tectonic and the LaTeX packages the resume uses."
        )
    )
    parser.add_argument("tex", type=Path, help="tailored resume .tex file")
    parser.add_argument(
        "--outdir", type=Path, default=None,
        help="directory for the PDF and log (default: the .tex file's directory)",
    )
    parser.add_argument(
        "--max-pages", type=int, default=1,
        help="warn when the PDF has more pages than this (default: 1)",
    )
    parser.add_argument(
        "--tectonic", type=Path, default=None,
        help="use this Tectonic executable instead of downloading the pinned version",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.tex.suffix != ".tex" or not args.tex.is_file():
        print(f"FAIL {args.tex}: not an existing .tex file", file=sys.stderr)
        return 1
    try:
        if args.tectonic is None:
            tectonic = ensure_tectonic()
        else:
            found = shutil.which(str(args.tectonic))
            if found is None:
                raise CompileError(f"Tectonic executable not found: {args.tectonic}")
            tectonic = Path(found)
        result = compile_resume(
            args.tex.resolve(),
            tectonic.resolve(),
            (args.outdir or args.tex.parent).resolve(),
            args.max_pages,
        )
    except CompileError as exc:
        print(f"FAIL {args.tex}: {exc}", file=sys.stderr)
        return 1

    if result.is_valid:
        pages = "unknown page count" if result.pages is None else (
            f"{result.pages} page" + ("" if result.pages == 1 else "s")
        )
        print(f"PASS {args.tex}: compiled to {result.pdf_path} ({pages})")
    else:
        print(f"FAIL {args.tex}: LaTeX compilation failed", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
    for warning in result.warnings:
        print(f"WARN {args.tex}: {warning}")
    return 0 if result.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
