#!/usr/bin/env python3
"""Check a generated tailored resume and its tailoring report deterministically."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from validate_candidate_data import UniqueKeySafeLoader, validate_candidate_directory


REPORT_VERSION = 1
REPORT_NAME_PATTERN = re.compile(r"^tailoring-report-([a-z0-9]+(?:-[a-z0-9]+)*)\.json$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RECORD_KINDS = {"experience", "project", "education"}
EVIDENCE_KINDS = RECORD_KINDS | {"accomplishment", "certification"}
REQUIREMENT_CATEGORIES = {"responsibility", "required", "preferred"}
REQUIREMENT_STATUSES = {"matched", "partial", "unmatched"}
REPORT_FIELDS = (
    "report_version",
    "job_description_path",
    "job",
    "canonical_template",
    "requirements",
    "keywords",
    "selected_records",
    "omitted_records",
    "profile",
    "bullets",
    "selected_skills",
    "unsupported_skills",
    "warnings",
    "ambiguities",
)
# Environments in which a bare & is an alignment character, not text.
ALIGNMENT_ENVIRONMENTS = {
    "tabular",
    "tabular*",
    "tabularx",
    "longtable",
    "array",
    "align",
    "align*",
    "alignat",
    "alignat*",
    "split",
    "matrix",
    "pmatrix",
    "bmatrix",
}
PLACEHOLDER_PATTERNS = (
    re.compile(r"\b(?:TODO|TBD|FIXME|XXX)\b"),
    re.compile(r"lorem ipsum", re.I),
    re.compile(r"\{\{\s*[A-Za-z_][\w .-]*\}\}"),
    re.compile(r"<[A-Za-z][A-Za-z _-]*>"),
    re.compile(r"\[(?:insert|add|placeholder)\b[^\]]*\]", re.I),
)
COMMENT_PATTERN = re.compile(r"(?<!\\)%[^\n]*")
UNESCAPED_PERCENT_PATTERN = re.compile(r"\d%")
# Arguments that hold URLs, file names, or labels rather than typeset text.
LITERAL_ARGUMENT_PATTERN = re.compile(
    r"(\\(?:href|url|includegraphics|input|include|label|ref|eqref|pageref)"
    r"\s*(?:\[[^\]]*\])?\s*\{)([^{}]*)(\})"
)
INLINE_MATH_PATTERN = re.compile(r"(?<!\\)\$(?:\\.|[^$\\])*\$", re.S)
STRUCTURE_TOKEN_PATTERN = re.compile(
    r"\\(begin|end)\s*\{([^{}]*)\}|\\[\\{}]|\\[A-Za-z@]+|\\.|[{}]", re.S
)
SPECIAL_TOKEN_PATTERN = re.compile(r"\\(begin|end)\s*\{([^{}]*)\}|\\.|[&#_]", re.S)
ITEM_PATTERN = re.compile(
    r"\\item\b\s*(?:\[[^\]]*\])?(.*?)"
    r"(?=\\item\b|\\end\s*\{(?:itemize|enumerate|description)\})",
    re.S,
)


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def error(self, location: str, message: str) -> None:
        self.errors.append(f"{location}: {message}")

    def warn(self, location: str, message: str) -> None:
        self.warnings.append(f"{location}: {message}")


@dataclass
class _CandidateIndex:
    kinds: dict[str, str] = field(default_factory=dict)
    parents: dict[str, str] = field(default_factory=dict)
    records: list[str] = field(default_factory=list)
    skill_evidence: dict[str, list[str]] = field(default_factory=dict)


def template_hash(path: Path) -> str:
    """Hash a template with normalized line endings."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def slugify(value: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def _normalize_space(text: str) -> str:
    return " ".join(text.split())


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


# Candidate data


def _load_candidate_index(candidate_dir: Path) -> _CandidateIndex:
    documents: dict[str, Any] = {}
    for filename in ("profile.yaml", "education.yaml", "experiences.yaml", "projects.yaml", "skills.yaml"):
        with (candidate_dir / filename).open("r", encoding="utf-8") as handle:
            documents[filename] = yaml.load(handle, Loader=UniqueKeySafeLoader)

    index = _CandidateIndex()
    profile = documents["profile.yaml"]
    index.kinds[profile["profile"]["id"]] = "profile"
    for link in profile["profile"]["links"]:
        index.kinds[link["id"]] = "link"
    for language in profile["languages"]:
        index.kinds[language["id"]] = "language"
        for item in language.get("supporting_information", []):
            index.kinds[item["id"]] = "language_support"
    for certification in profile["certifications"]:
        index.kinds[certification["id"]] = "certification"

    for filename, root_name, kind in (
        ("experiences.yaml", "experiences", "experience"),
        ("projects.yaml", "projects", "project"),
        ("education.yaml", "education", "education"),
    ):
        for record in documents[filename][root_name]:
            index.kinds[record["id"]] = kind
            index.records.append(record["id"])
            for accomplishment in record["accomplishments"]:
                index.kinds[accomplishment["id"]] = "accomplishment"
                index.parents[accomplishment["id"]] = record["id"]

    for group in documents["skills.yaml"]["skill_groups"]:
        index.kinds[group["id"]] = "skill_group"
        for skill in group["skills"]:
            index.kinds[skill["id"]] = "skill"
            index.skill_evidence[skill["id"]] = skill["evidence_ids"]
    return index


# Report structure


def _check_keys(
    value: Any,
    location: str,
    required: tuple[str, ...],
    result: CheckResult,
    optional: tuple[str, ...] = (),
) -> bool:
    if not isinstance(value, dict):
        result.error(location, "must be an object")
        return False
    for key in required:
        if key not in value:
            result.error(f"{location}.{key}", "required field is missing")
    for key in value:
        if key not in required and key not in optional:
            result.error(f"{location}.{key}", "unexpected field")
    return all(key in value for key in required)


def _is_string(value: Any, location: str, result: CheckResult) -> bool:
    if not isinstance(value, str) or not value.strip():
        result.error(location, "must be a non-empty string")
        return False
    return True


def _string_list(
    value: Any, location: str, result: CheckResult, *, allow_empty: bool = True
) -> list[str]:
    if not isinstance(value, list):
        result.error(location, "must be a list")
        return []
    if not value and not allow_empty:
        result.error(location, "must contain at least one item")
    strings = []
    for index, item in enumerate(value):
        if _is_string(item, f"{location}[{index}]", result):
            strings.append(item)
    return strings


def _object_list(value: Any, location: str, result: CheckResult) -> list[tuple[str, Any]]:
    if not isinstance(value, list):
        result.error(location, "must be a list")
        return []
    return [(f"{location}[{index}]", item) for index, item in enumerate(value)]


def _check_cited_ids(
    ids: list[str],
    location: str,
    allowed_kinds: set[str] | None,
    index: _CandidateIndex | None,
    result: CheckResult,
) -> None:
    if index is None:
        return
    for position, identifier in enumerate(ids):
        kind = index.kinds.get(identifier)
        if kind is None:
            result.error(f"{location}[{position}]", f"cites unknown candidate ID {identifier!r}")
        elif allowed_kinds is not None and kind not in allowed_kinds:
            result.error(
                f"{location}[{position}]",
                f"cites {identifier!r}, a {kind} ID; expected one of "
                + ", ".join(sorted(allowed_kinds)),
            )


def _check_job(report: dict[str, Any], suffix: str, root: Path, result: CheckResult) -> None:
    job_path_value = report.get("job_description_path")
    if _is_string(job_path_value, "report.job_description_path", result):
        job_path = root / job_path_value
        if not job_path.is_file():
            result.error("report.job_description_path", f"file does not exist: {job_path_value}")
        elif job_path.stem != suffix:
            result.warn(
                "report.job_description_path",
                f"file name {job_path.name!r} does not match output suffix {suffix!r}",
            )

    job = report.get("job")
    if not _check_keys(job, "report.job", ("company", "location", "role", "seniority"), result):
        return
    company_ok = _is_string(job["company"], "report.job.company", result)
    location_ok = _is_string(job["location"], "report.job.location", result)
    _is_string(job["role"], "report.job.role", result)
    if job["seniority"] is not None:
        _is_string(job["seniority"], "report.job.seniority", result)
    if company_ok and location_ok:
        expected = f"{slugify(job['company'])}-{slugify(job['location'])}"
        if expected != suffix:
            result.error(
                "report.job",
                f"company and location give suffix {expected!r}, but the files use {suffix!r}",
            )


def _check_template(
    report: dict[str, Any], template_path: Path, root: Path, result: CheckResult
) -> None:
    template = report.get("canonical_template")
    location = "report.canonical_template"
    if not _check_keys(template, location, ("path", "sha256_before", "sha256_after"), result):
        return
    if _is_string(template["path"], f"{location}.path", result):
        if (root / template["path"]).resolve() != template_path.resolve():
            result.error(
                f"{location}.path",
                f"{template['path']!r} is not the template being checked ({template_path})",
            )
    if not template_path.is_file():
        result.error(location, f"template file does not exist: {template_path}")
        return
    current = template_hash(template_path)
    for key in ("sha256_before", "sha256_after"):
        value = template[key]
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            result.error(f"{location}.{key}", "must be a lowercase 64-character SHA-256 hex digest")
        elif value != current:
            result.error(
                f"{location}.{key}",
                "does not match the current template; the canonical template may have been modified",
            )


def _check_requirements(
    report: dict[str, Any], index: _CandidateIndex | None, result: CheckResult
) -> None:
    items = _object_list(report.get("requirements"), "report.requirements", result)
    if isinstance(report.get("requirements"), list) and not items:
        result.error("report.requirements", "must contain at least one item")
    for location, item in items:
        if not _check_keys(
            item, location, ("text", "category", "status", "evidence_ids"), result, ("note",)
        ):
            continue
        _is_string(item["text"], f"{location}.text", result)
        if item["category"] not in REQUIREMENT_CATEGORIES:
            result.error(f"{location}.category", "must be one of " + ", ".join(sorted(REQUIREMENT_CATEGORIES)))
        if item["status"] not in REQUIREMENT_STATUSES:
            result.error(f"{location}.status", "must be one of " + ", ".join(sorted(REQUIREMENT_STATUSES)))
        evidence = _string_list(item["evidence_ids"], f"{location}.evidence_ids", result)
        if item["status"] == "unmatched" and item["evidence_ids"]:
            result.error(f"{location}.evidence_ids", "must be empty for an unmatched requirement")
        if item["status"] in {"matched", "partial"} and not item["evidence_ids"]:
            result.error(f"{location}.evidence_ids", f"must cite evidence for a {item['status']} requirement")
        _check_cited_ids(evidence, f"{location}.evidence_ids", EVIDENCE_KINDS, index, result)
        if "note" in item:
            _is_string(item["note"], f"{location}.note", result)
    _string_list(report.get("keywords"), "report.keywords", result, allow_empty=False)


def _check_records(
    report: dict[str, Any], index: _CandidateIndex | None, result: CheckResult
) -> set[str]:
    seen: dict[str, str] = {}
    selected: set[str] = set()
    for field_name in ("selected_records", "omitted_records"):
        for location, item in _object_list(report.get(field_name), f"report.{field_name}", result):
            if not _check_keys(item, location, ("id", "reason"), result):
                continue
            _is_string(item["reason"], f"{location}.reason", result)
            if not _is_string(item["id"], f"{location}.id", result):
                continue
            _check_cited_ids([item["id"]], f"{location}.id", RECORD_KINDS, index, result)
            if item["id"] in seen:
                result.error(f"{location}.id", f"{item['id']!r} is already listed at {seen[item['id']]}")
                continue
            seen[item["id"]] = location
            if field_name == "selected_records":
                selected.add(item["id"])
    if index is not None:
        for record_id in index.records:
            if record_id not in seen:
                result.error(
                    "report",
                    f"record {record_id!r} must be listed in selected_records or omitted_records",
                )
    return selected


def _check_bullets(
    report: dict[str, Any],
    selected_records: set[str],
    index: _CandidateIndex | None,
    result: CheckResult,
) -> list[str]:
    bullets: list[str] = []
    for location, item in _object_list(report.get("bullets"), "report.bullets", result):
        if not _check_keys(item, location, ("record_id", "latex", "source_ids"), result):
            continue
        if _is_string(item["latex"], f"{location}.latex", result):
            bullets.append(item["latex"])
        sources = _string_list(item["source_ids"], f"{location}.source_ids", result, allow_empty=False)
        record_id = item["record_id"]
        if not _is_string(record_id, f"{location}.record_id", result):
            continue
        if record_id not in selected_records:
            result.error(f"{location}.record_id", f"{record_id!r} is not in selected_records")
        if index is None:
            continue
        for position, source in enumerate(sources):
            if source == record_id or index.parents.get(source) == record_id:
                continue
            if source not in index.kinds:
                message = f"cites unknown candidate ID {source!r}"
            else:
                message = f"{source!r} is not {record_id!r} or one of its accomplishments"
            result.error(f"{location}.source_ids[{position}]", message)
    return bullets


def _check_profile(
    report: dict[str, Any], index: _CandidateIndex | None, result: CheckResult
) -> str | None:
    profile = report.get("profile")
    if not _check_keys(profile, "report.profile", ("latex", "source_ids"), result):
        return None
    sources = _string_list(profile["source_ids"], "report.profile.source_ids", result, allow_empty=False)
    _check_cited_ids(sources, "report.profile.source_ids", None, index, result)
    if _is_string(profile["latex"], "report.profile.latex", result):
        return profile["latex"]
    return None


def _check_skills(
    report: dict[str, Any], index: _CandidateIndex | None, result: CheckResult
) -> None:
    selected = _string_list(report.get("selected_skills"), "report.selected_skills", result)
    unsupported = _string_list(report.get("unsupported_skills"), "report.unsupported_skills", result)
    _check_cited_ids(selected, "report.selected_skills", {"skill"}, index, result)
    _check_cited_ids(unsupported, "report.unsupported_skills", {"skill"}, index, result)
    if index is None:
        return
    for skill_id in selected:
        if index.kinds.get(skill_id) == "skill" and not index.skill_evidence[skill_id]:
            if skill_id not in unsupported:
                result.error(
                    "report.unsupported_skills",
                    f"must list {skill_id!r}, a selected skill with no evidence_ids",
                )
    for position, skill_id in enumerate(unsupported):
        location = f"report.unsupported_skills[{position}]"
        if skill_id not in selected:
            result.error(location, f"{skill_id!r} is not in selected_skills")
        elif index.skill_evidence.get(skill_id):
            result.error(location, f"{skill_id!r} has evidence_ids in skills.yaml")


# LaTeX


def _check_structure(text: str, result: CheckResult, location: str) -> None:
    stripped = COMMENT_PATTERN.sub(lambda match: _blank(match.group(0)), text)
    open_braces: list[int] = []
    environments: list[tuple[str, int]] = []
    for match in STRUCTURE_TOKEN_PATTERN.finditer(stripped):
        token = match.group(0)
        line = _line_number(stripped, match.start())
        if match.group(1) == "begin":
            environments.append((match.group(2), line))
        elif match.group(1) == "end":
            name = match.group(2)
            if not environments:
                result.error(f"{location}:{line}", f"\\end{{{name}}} has no matching \\begin")
            elif environments[-1][0] != name:
                open_name, open_line = environments.pop()
                result.error(
                    f"{location}:{line}",
                    f"\\end{{{name}}} closes \\begin{{{open_name}}} from line {open_line}",
                )
            else:
                environments.pop()
        elif token == "{":
            open_braces.append(line)
        elif token == "}":
            if open_braces:
                open_braces.pop()
            else:
                result.error(f"{location}:{line}", "closing brace has no matching opening brace")
    for line in open_braces:
        result.error(f"{location}:{line}", "opening brace is never closed")
    for name, line in environments:
        result.error(f"{location}:{line}", f"\\begin{{{name}}} is never closed")


def _check_body_text(body: str, body_start_line: int, result: CheckResult, location: str) -> None:
    def where(text: str, offset: int) -> str:
        return f"{location}:{body_start_line + _line_number(text, offset) - 1}"

    for match in UNESCAPED_PERCENT_PATTERN.finditer(body):
        result.error(
            where(body, match.start()),
            "unescaped % after a number comments out the rest of the line; use \\%",
        )

    stripped = COMMENT_PATTERN.sub(lambda match: _blank(match.group(0)), body)
    for pattern in PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(stripped):
            result.error(where(stripped, match.start()), f"unresolved placeholder {match.group(0)!r}")

    text = LITERAL_ARGUMENT_PATTERN.sub(
        lambda match: match.group(1) + _blank(match.group(2)) + match.group(3), stripped
    )
    text = INLINE_MATH_PATTERN.sub(lambda match: _blank(match.group(0)), text)
    environments: list[str] = []
    for match in SPECIAL_TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        if match.group(1) == "begin":
            environments.append(match.group(2))
        elif match.group(1) == "end":
            if environments and environments[-1] == match.group(2):
                environments.pop()
        elif token == "&" and any(name in ALIGNMENT_ENVIRONMENTS for name in environments):
            continue
        elif token in {"&", "#", "_"}:
            result.error(where(text, match.start()), f"unescaped {token}; use \\{token}")


def _check_tex(
    tex_path: Path,
    template_path: Path,
    profile_latex: str | None,
    report_bullets: list[str],
    result: CheckResult,
) -> None:
    location = tex_path.name
    try:
        text = tex_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeError) as exc:
        result.error(location, f"could not read UTF-8 LaTeX ({exc.__class__.__name__})")
        return

    _check_structure(text, result, location)
    marker = "\\begin{document}"
    start = text.find(marker)
    if start < 0 or "\\end{document}" not in text:
        result.error(location, "must contain \\begin{document} and \\end{document}")
        return
    body_offset = start + len(marker)
    body = text[body_offset:]
    _check_body_text(body, _line_number(text, body_offset), result, location)

    if template_path.is_file():
        template_text = template_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        template_start = template_text.find(marker)
        if template_start >= 0 and template_text[:template_start] != text[:start]:
            result.warn(location, "preamble differs from the canonical template")

    stripped_body = COMMENT_PATTERN.sub("", body)
    tex_items = Counter(_normalize_space(match.group(1)) for match in ITEM_PATTERN.finditer(stripped_body))
    reported = Counter(_normalize_space(bullet) for bullet in report_bullets)
    for item in sorted((tex_items - reported).elements()):
        result.error(location, f"\\item is not recorded in report.bullets: {item!r}")
    for item in sorted((reported - tex_items).elements()):
        result.error("report.bullets", f"bullet does not appear as an \\item in {location}: {item!r}")

    if profile_latex is not None and _normalize_space(profile_latex) not in _normalize_space(stripped_body):
        result.error("report.profile.latex", f"does not appear in {location}")


# Entry points


def check_outputs(
    report_path: Path | str,
    candidate_dir: Path | str,
    template_path: Path | str,
    root: Path | str = ".",
) -> CheckResult:
    report_path = Path(report_path)
    candidate_dir = Path(candidate_dir)
    template_path = Path(template_path)
    root = Path(root)
    result = CheckResult()

    name_match = REPORT_NAME_PATTERN.fullmatch(report_path.name)
    if not name_match:
        result.error(
            report_path.name,
            "report file must be named tailoring-report-<company>-<location>.json "
            "with a lowercase hyphenated suffix",
        )
        return result
    suffix = name_match.group(1)
    tex_path = report_path.with_name(f"tailored-resume-{suffix}.tex")
    if not tex_path.is_file():
        result.error(tex_path.name, "matching tailored resume does not exist")

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result.error(report_path.name, f"could not read JSON ({exc.__class__.__name__})")
        return result
    if not _check_keys(report, "report", REPORT_FIELDS, result):
        return result
    if report["report_version"] != REPORT_VERSION:
        result.error("report.report_version", f"must be {REPORT_VERSION}")

    validation = validate_candidate_directory(candidate_dir)
    index: _CandidateIndex | None = None
    if validation.is_valid:
        index = _load_candidate_index(candidate_dir)
    else:
        result.error(
            str(candidate_dir),
            "candidate data fails validation; run scripts/validate_candidate_data.py",
        )

    _check_job(report, suffix, root, result)
    _check_template(report, template_path, root, result)
    _check_requirements(report, index, result)
    selected_records = _check_records(report, index, result)
    profile_latex = _check_profile(report, index, result)
    bullets = _check_bullets(report, selected_records, index, result)
    _check_skills(report, index, result)
    warnings = _string_list(report["warnings"], "report.warnings", result)
    _string_list(report["ambiguities"], "report.ambiguities", result)
    for warning in validation.warnings:
        if warning not in warnings:
            result.error("report.warnings", f"must include the validator warning {warning!r}")

    if tex_path.is_file():
        _check_tex(tex_path, template_path, profile_latex, bullets, result)

    result.errors = sorted(set(result.errors))
    result.warnings = sorted(set(result.warnings))
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check generated tailoring outputs and fingerprint the canonical template."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    hash_parser = commands.add_parser(
        "template-hash", help="print the canonical template's SHA-256 fingerprint"
    )
    hash_parser.add_argument(
        "--template", type=Path, default=Path("templates/resume.tex"),
        help="canonical template (default: templates/resume.tex)",
    )

    check_parser = commands.add_parser(
        "check", help="check a tailoring report and its matching tailored resume"
    )
    check_parser.add_argument("report", type=Path, help="path to tailoring-report-<suffix>.json")
    check_parser.add_argument(
        "--candidate", type=Path, default=Path("candidate"),
        help="candidate directory (default: candidate)",
    )
    check_parser.add_argument(
        "--template", type=Path, default=Path("templates/resume.tex"),
        help="canonical template (default: templates/resume.tex)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "template-hash":
        if not args.template.is_file():
            print(f"FAIL {args.template}: template file does not exist", file=sys.stderr)
            return 1
        print(template_hash(args.template))
        return 0

    result = check_outputs(args.report, args.candidate, args.template, Path.cwd())
    if result.is_valid:
        print(f"PASS {args.report}: report and tailored resume are consistent")
    else:
        print(f"FAIL {args.report}:", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
    for warning in result.warnings:
        print(f"WARN {warning}")
    return 0 if result.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
