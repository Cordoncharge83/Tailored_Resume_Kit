#!/usr/bin/env python3
"""Validate Tailored Resume Kit candidate YAML deterministically."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


EXPECTED_FILES = (
    "profile.yaml",
    "education.yaml",
    "experiences.yaml",
    "projects.yaml",
    "skills.yaml",
)
ALLOWED_EXPERIENCE_TYPES = {
    "professional",
    "internship",
    "volunteering",
    "leadership",
}
ALLOWED_PROJECT_TYPES = {"personal", "academic"}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DATE_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeySafeLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass
class ValidationResult:
    directory: Path
    errors: list[str] = field(default_factory=list)
    id_count: int = 0
    evidence_reference_count: int = 0

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass
class _ValidationState:
    errors: list[str] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)
    evidence_references: list[tuple[str, str]] = field(default_factory=list)

    def error(self, location: str, message: str) -> None:
        self.errors.append(f"{location}: {message}")


def _is_mapping(value: Any, location: str, state: _ValidationState) -> bool:
    if not isinstance(value, dict):
        state.error(location, "must be a mapping")
        return False
    return True


def _is_list(value: Any, location: str, state: _ValidationState) -> bool:
    if not isinstance(value, list):
        state.error(location, "must be a list")
        return False
    return True


def _required_fields(
    mapping: dict[str, Any], fields: Iterable[str], location: str, state: _ValidationState
) -> None:
    for field_name in fields:
        if field_name not in mapping:
            state.error(f"{location}.{field_name}", "required field is missing")


def _string_field(
    mapping: dict[str, Any],
    field_name: str,
    location: str,
    state: _ValidationState,
    *,
    required: bool = True,
) -> str | None:
    if field_name not in mapping:
        if required:
            state.error(f"{location}.{field_name}", "required field is missing")
        return None
    value = mapping[field_name]
    if not isinstance(value, str) or not value.strip():
        state.error(f"{location}.{field_name}", "must be a non-empty string")
        return None
    return value


def _string_list_field(
    mapping: dict[str, Any],
    field_name: str,
    location: str,
    state: _ValidationState,
    *,
    required: bool = True,
) -> list[str] | None:
    if field_name not in mapping:
        if required:
            state.error(f"{location}.{field_name}", "required field is missing")
        return None
    value = mapping[field_name]
    field_location = f"{location}.{field_name}"
    if not _is_list(value, field_location, state):
        return None
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            state.error(f"{field_location}[{index}]", "must be a non-empty string")
    return value


def _mapping_items(
    mapping: dict[str, Any],
    field_name: str,
    location: str,
    state: _ValidationState,
    *,
    required: bool = True,
) -> list[Any] | None:
    if field_name not in mapping:
        if required:
            state.error(f"{location}.{field_name}", "required field is missing")
        return None
    value = mapping[field_name]
    field_location = f"{location}.{field_name}"
    if not _is_list(value, field_location, state):
        return None
    return value


def _date_field(
    mapping: dict[str, Any],
    field_name: str,
    location: str,
    state: _ValidationState,
    *,
    allow_present: bool = False,
) -> str | None:
    value = _string_field(mapping, field_name, location, state)
    if value is None:
        return None
    if allow_present and value == "present":
        return value
    if not DATE_PATTERN.fullmatch(value):
        state.error(
            f"{location}.{field_name}",
            "must use YYYY-MM format" + (" or 'present'" if allow_present else ""),
        )
        return None
    return value


def _date_order(
    start_date: str | None, end_date: str | None, location: str, state: _ValidationState
) -> None:
    if (
        start_date
        and end_date
        and end_date != "present"
        and DATE_PATTERN.fullmatch(start_date)
        and DATE_PATTERN.fullmatch(end_date)
        and end_date < start_date
    ):
        state.error(location, "end_date must not precede start_date")


def _accomplishments(
    mapping: dict[str, Any], location: str, state: _ValidationState
) -> None:
    items = _mapping_items(mapping, "accomplishments", location, state)
    if items is None:
        return
    if not items:
        state.error(f"{location}.accomplishments", "must contain at least one item")
    for index, item in enumerate(items):
        item_location = f"{location}.accomplishments[{index}]"
        if not _is_mapping(item, item_location, state):
            continue
        _string_field(item, "id", item_location, state)
        _string_field(item, "text", item_location, state)
        if "historical" in item and not isinstance(item["historical"], bool):
            state.error(f"{item_location}.historical", "must be a boolean")


def _validate_profile(data: Any, source: str, state: _ValidationState) -> None:
    if not _is_mapping(data, f"{source}$", state):
        return
    allowed_roots = {"profile", "languages", "certifications"}
    for key in data:
        if key not in allowed_roots:
            state.error(f"{source}$.{key}", "unexpected top-level field")
    _required_fields(data, allowed_roots, f"{source}$", state)

    profile = data.get("profile")
    if _is_mapping(profile, f"{source}$.profile", state):
        location = f"{source}$.profile"
        for field_name in ("id", "name", "headline", "summary", "email"):
            _string_field(profile, field_name, location, state)
        _string_field(profile, "phone", location, state, required=False)
        links = _mapping_items(profile, "links", location, state)
        if links is not None:
            for index, link in enumerate(links):
                link_location = f"{location}.links[{index}]"
                if not _is_mapping(link, link_location, state):
                    continue
                for field_name in ("id", "label", "url"):
                    _string_field(link, field_name, link_location, state)

    languages = data.get("languages")
    if _is_list(languages, f"{source}$.languages", state):
        for index, language in enumerate(languages):
            location = f"{source}$.languages[{index}]"
            if not _is_mapping(language, location, state):
                continue
            for field_name in ("id", "name", "proficiency"):
                _string_field(language, field_name, location, state)
            supporting = _mapping_items(
                language, "supporting_information", location, state, required=False
            )
            if supporting is not None:
                for support_index, item in enumerate(supporting):
                    support_location = (
                        f"{location}.supporting_information[{support_index}]"
                    )
                    if not _is_mapping(item, support_location, state):
                        continue
                    for field_name in ("id", "type", "name"):
                        _string_field(item, field_name, support_location, state)
                    _string_field(item, "score", support_location, state, required=False)
                    if "historical" in item and not isinstance(item["historical"], bool):
                        state.error(
                            f"{support_location}.historical", "must be a boolean"
                        )

    certifications = data.get("certifications")
    if _is_list(certifications, f"{source}$.certifications", state):
        for index, certification in enumerate(certifications):
            location = f"{source}$.certifications[{index}]"
            if not _is_mapping(certification, location, state):
                continue
            _string_field(certification, "id", location, state)
            _string_field(certification, "name", location, state)


def _validate_education(data: Any, source: str, state: _ValidationState) -> None:
    if not _validate_single_root(data, source, "education", state):
        return
    for index, item in enumerate(data["education"]):
        location = f"{source}$.education[{index}]"
        if not _is_mapping(item, location, state):
            continue
        for field_name in (
            "id",
            "institution",
            "degree",
            "field_of_study",
            "location",
        ):
            _string_field(item, field_name, location, state)
        start = _date_field(item, "start_date", location, state)
        end = _date_field(item, "end_date", location, state, allow_present=True)
        _date_order(start, end, location, state)
        _accomplishments(item, location, state)


def _validate_experiences(data: Any, source: str, state: _ValidationState) -> None:
    if not _validate_single_root(data, source, "experiences", state):
        return
    for index, item in enumerate(data["experiences"]):
        location = f"{source}$.experiences[{index}]"
        if not _is_mapping(item, location, state):
            continue
        _string_field(item, "id", location, state)
        experience_type = _string_field(item, "experience_type", location, state)
        if experience_type and experience_type not in ALLOWED_EXPERIENCE_TYPES:
            state.error(
                f"{location}.experience_type",
                "must be one of professional, internship, volunteering, leadership",
            )
        if experience_type in {"professional", "internship"}:
            _string_field(item, "employer", location, state)
        elif experience_type in {"volunteering", "leadership"}:
            _string_field(item, "organization", location, state)
        _string_field(item, "role", location, state)
        _string_field(item, "location", location, state, required=False)
        start = _date_field(item, "start_date", location, state)
        end = _date_field(item, "end_date", location, state, allow_present=True)
        _date_order(start, end, location, state)
        _string_list_field(item, "technologies", location, state, required=False)
        _accomplishments(item, location, state)


def _validate_projects(data: Any, source: str, state: _ValidationState) -> None:
    if not _validate_single_root(data, source, "projects", state):
        return
    for index, item in enumerate(data["projects"]):
        location = f"{source}$.projects[{index}]"
        if not _is_mapping(item, location, state):
            continue
        for field_name in ("id", "name", "description"):
            _string_field(item, field_name, location, state)
        project_type = _string_field(item, "project_type", location, state)
        if project_type and project_type not in ALLOWED_PROJECT_TYPES:
            state.error(
                f"{location}.project_type", "must be one of personal, academic"
            )
        _string_list_field(item, "technologies", location, state)
        for optional_url in ("url", "repository_url"):
            _string_field(item, optional_url, location, state, required=False)
        _accomplishments(item, location, state)


def _validate_skills(data: Any, source: str, state: _ValidationState) -> None:
    if not _validate_single_root(data, source, "skill_groups", state):
        return
    seen_names: dict[str, str] = {}
    for group_index, group in enumerate(data["skill_groups"]):
        group_location = f"{source}$.skill_groups[{group_index}]"
        if not _is_mapping(group, group_location, state):
            continue
        _string_field(group, "id", group_location, state)
        _string_field(group, "name", group_location, state)
        skills = _mapping_items(group, "skills", group_location, state)
        if skills is None:
            continue
        for skill_index, skill in enumerate(skills):
            location = f"{group_location}.skills[{skill_index}]"
            if not _is_mapping(skill, location, state):
                continue
            _string_field(skill, "id", location, state)
            name = _string_field(skill, "name", location, state)
            _string_list_field(skill, "evidence_ids", location, state)
            if name:
                normalized = name.strip().casefold()
                if normalized in seen_names:
                    state.error(
                        f"{location}.name",
                        f"duplicates the skill name at {seen_names[normalized]}",
                    )
                else:
                    seen_names[normalized] = f"{location}.name"


def _validate_single_root(
    data: Any, source: str, root_name: str, state: _ValidationState
) -> bool:
    if not _is_mapping(data, f"{source}$", state):
        return False
    for key in data:
        if key != root_name:
            state.error(f"{source}$.{key}", "unexpected top-level field")
    if root_name not in data:
        state.error(f"{source}$.{root_name}", "required field is missing")
        return False
    return _is_list(data[root_name], f"{source}$.{root_name}", state)


VALIDATORS = {
    "profile.yaml": _validate_profile,
    "education.yaml": _validate_education,
    "experiences.yaml": _validate_experiences,
    "projects.yaml": _validate_projects,
    "skills.yaml": _validate_skills,
}


def _load_yaml(path: Path, state: _ValidationState) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.load(handle, Loader=UniqueKeySafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        state.error(path.name, f"could not parse safe YAML ({exc.__class__.__name__})")
        return None


def _collect_identifiers(
    value: Any,
    location: str,
    state: _ValidationState,
    seen_containers: set[int] | None = None,
) -> None:
    if seen_containers is None:
        seen_containers = set()
    if isinstance(value, (dict, list)):
        identity = id(value)
        if identity in seen_containers:
            state.error(location, "reused or recursive YAML aliases are not allowed")
            return
        seen_containers.add(identity)
    if isinstance(value, dict):
        identifier = value.get("id")
        if identifier is not None:
            id_location = f"{location}.id"
            if not isinstance(identifier, str) or not identifier.strip():
                state.error(id_location, "must be a non-empty string")
            elif not ID_PATTERN.fullmatch(identifier):
                state.error(
                    id_location,
                    "must start with a lowercase letter and contain only lowercase letters, digits, and underscores",
                )
            elif identifier in state.ids:
                state.error(
                    id_location,
                    f"duplicates the ID at {state.ids[identifier]}",
                )
            else:
                state.ids[identifier] = id_location

        references = value.get("evidence_ids")
        if isinstance(references, list):
            for index, reference in enumerate(references):
                if isinstance(reference, str) and reference.strip():
                    state.evidence_references.append(
                        (reference, f"{location}.evidence_ids[{index}]")
                    )

        for key, child in value.items():
            _collect_identifiers(
                child, f"{location}.{key}", state, seen_containers
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_identifiers(
                child, f"{location}[{index}]", state, seen_containers
            )


def validate_candidate_directory(directory: Path | str) -> ValidationResult:
    candidate_dir = Path(directory)
    state = _ValidationState()
    documents: dict[str, Any] = {}

    if not candidate_dir.is_dir():
        return ValidationResult(
            directory=candidate_dir,
            errors=[f"{candidate_dir}: candidate directory does not exist"],
        )

    present_yaml = {path.name for path in candidate_dir.glob("*.yaml")}
    expected = set(EXPECTED_FILES)
    for missing in sorted(expected - present_yaml):
        state.error(missing, "required candidate file is missing")
    for unexpected in sorted(present_yaml - expected):
        state.error(unexpected, "unexpected candidate YAML file")

    for filename in EXPECTED_FILES:
        path = candidate_dir / filename
        if not path.is_file():
            continue
        document = _load_yaml(path, state)
        if document is None:
            continue
        documents[filename] = document
        VALIDATORS[filename](document, filename, state)
        _collect_identifiers(document, f"{filename}$", state)

    for reference, location in state.evidence_references:
        if reference not in state.ids:
            state.error(location, "references an ID that does not exist")

    return ValidationResult(
        directory=candidate_dir,
        errors=sorted(set(state.errors)),
        id_count=len(state.ids),
        evidence_reference_count=len(state.evidence_references),
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate candidate YAML syntax, structure, IDs, and evidence references."
    )
    parser.add_argument(
        "directories",
        nargs="*",
        type=Path,
        default=[Path("examples/candidate")],
        help="candidate directories to validate (default: examples/candidate)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    failed = False
    for directory in args.directories:
        result = validate_candidate_directory(directory)
        if result.is_valid:
            print(
                f"PASS {directory}: 5 files, {result.id_count} unique IDs, "
                f"{result.evidence_reference_count} valid evidence references"
            )
            continue
        failed = True
        print(f"FAIL {directory}:", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
