#!/usr/bin/env python3
"""Reject private paths and high-confidence secrets from the publishable tree."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


FORBIDDEN_PREFIXES = ("candidate/", "inputs/", "output/", "references/")
FORBIDDEN_EXACT_PATHS = {"templates/resume.tex"}
REQUIRED_IGNORE_PROBES = (
    "candidate/profile.yaml",
    "inputs/example-company-remote.txt",
    "output/tailored-resume-example-company-remote.tex",
    "references/example-resume.pdf",
    "templates/resume.tex",
)
SECRET_PATTERNS = {
    "private key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "OpenAI-style secret key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.I)
URL_PATTERN = re.compile(r"https?://[^\s<>\"'{}\[\]]+")
PHONE_PATTERN = re.compile(r"\+\d[\d\s().-]{6,}\d")
WINDOWS_HOME_PATTERN = re.compile(r"\b[A-Z]:\\Users\\[^\\\s]+", re.I)
UNIX_HOME_PATTERN = re.compile(r"(?<![A-Za-z0-9_])/home/[A-Za-z0-9._-]+")


def discover_publishable_files(root: Path) -> tuple[list[str], list[str]]:
    """Return non-ignored tracked and untracked files, plus discovery errors."""
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return [], ["could not inventory publishable files with Git"]
    decoded = completed.stdout.decode("utf-8", errors="strict")
    return sorted(path for path in decoded.split("\0") if path), []


def _is_example_identity_file(relative_path: str) -> bool:
    return (
        relative_path.startswith("examples/candidate/")
        or relative_path.startswith("examples/inputs/")
        or relative_path.startswith("examples/output/")
        or relative_path == "templates/resume.example.tex"
    )


def check_paths(root: Path, relative_paths: list[str]) -> list[str]:
    errors: list[str] = []
    for original_path in sorted(set(relative_paths)):
        relative_path = original_path.replace("\\", "/")
        if relative_path in FORBIDDEN_EXACT_PATHS or relative_path.startswith(
            FORBIDDEN_PREFIXES
        ):
            errors.append(f"{relative_path}: private working path would be published")
            continue
        name = Path(relative_path).name
        if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
            errors.append(f"{relative_path}: local environment file would be published")
        if relative_path.lower().endswith(".pdf"):
            errors.append(f"{relative_path}: PDF files require explicit privacy review")

        path = root / Path(relative_path)
        try:
            raw = path.read_bytes()
        except OSError:
            errors.append(f"{relative_path}: file could not be read")
            continue
        if b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{relative_path}: text file must be UTF-8")
            continue

        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{relative_path}: contains a possible {label}")
        if WINDOWS_HOME_PATTERN.search(text) or UNIX_HOME_PATTERN.search(text):
            errors.append(f"{relative_path}: contains a user-specific absolute path")

        if _is_example_identity_file(relative_path):
            for match in EMAIL_PATTERN.finditer(text):
                if match.group(1).casefold() != "example.com":
                    errors.append(
                        f"{relative_path}: example data contains a non-example email domain"
                    )
                    break
            for match in URL_PATTERN.finditer(text):
                hostname = (urlparse(match.group(0)).hostname or "").casefold()
                if hostname != "example.com" and not hostname.endswith(".example.com"):
                    errors.append(
                        f"{relative_path}: example data contains a non-example URL domain"
                    )
                    break
            for match in PHONE_PATTERN.finditer(text):
                digits = "".join(character for character in match.group(0) if character.isdigit())
                if set(digits) != {"0"}:
                    errors.append(
                        f"{relative_path}: example data contains a non-placeholder phone number"
                    )
                    break

        if relative_path.startswith("examples/inputs/"):
            if not name.startswith("example-"):
                errors.append(
                    f"{relative_path}: public job-description examples must start with 'example-'"
                )
            if "Example" not in text:
                errors.append(
                    f"{relative_path}: public job-description example lacks an explicit fictional marker"
                )
    return sorted(set(errors))


def check_ignore_rules(root: Path) -> list[str]:
    errors: list[str] = []
    for probe in REQUIRED_IGNORE_PROBES:
        completed = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--quiet", "--no-index", probe],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            errors.append(f".gitignore does not protect {probe}")
    return errors


def check_repository(root: Path) -> tuple[list[str], int]:
    paths, errors = discover_publishable_files(root)
    errors.extend(check_paths(root, paths))
    errors.extend(check_ignore_rules(root))
    return sorted(set(errors)), len(paths)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors, file_count = check_repository(root)
    if errors:
        print("FAIL public release safeguards:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"PASS public release safeguards: {file_count} publishable files; "
        "private paths remain ignored; no high-confidence secrets detected"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
