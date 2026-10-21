from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_candidate_data import validate_candidate_directory  # noqa: E402


class CandidateValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.candidate_dir = Path(self._temporary_directory.name) / "candidate"
        shutil.copytree(ROOT / "examples" / "candidate", self.candidate_dir)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _load(self, filename: str) -> dict:
        with (self.candidate_dir / filename).open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def _save(self, filename: str, data: dict) -> None:
        with (self.candidate_dir / filename).open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)

    def test_public_examples_are_valid(self) -> None:
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(result.is_valid, result.errors)
        self.assertEqual(result.id_count, 27)
        self.assertEqual(result.evidence_reference_count, 6)

    def test_duplicate_yaml_key_is_rejected(self) -> None:
        profile_path = self.candidate_dir / "profile.yaml"
        with profile_path.open("a", encoding="utf-8") as handle:
            handle.write("\nprofile: {}\n")
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(any("could not parse safe YAML" in error for error in result.errors))

    def test_duplicate_id_is_rejected_across_files(self) -> None:
        education = self._load("education.yaml")
        education["education"][0]["id"] = "profile_example_candidate"
        self._save("education.yaml", education)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(any("duplicates the ID" in error for error in result.errors))

    def test_missing_evidence_reference_is_rejected(self) -> None:
        skills = self._load("skills.yaml")
        skills["skill_groups"][0]["skills"][0]["evidence_ids"] = [
            "accomplishment_does_not_exist"
        ]
        self._save("skills.yaml", skills)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(
            any("references an ID that does not exist" in error for error in result.errors)
        )

    def test_evidence_may_reference_an_existing_record_id(self) -> None:
        skills = self._load("skills.yaml")
        skills["skill_groups"][0]["skills"][0]["evidence_ids"] = [
            "project_example_task_manager"
        ]
        self._save("skills.yaml", skills)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(result.is_valid, result.errors)

    def test_invalid_experience_type_is_rejected(self) -> None:
        experiences = self._load("experiences.yaml")
        experiences["experiences"][0]["experience_type"] = "contract"
        self._save("experiences.yaml", experiences)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(any("experience_type" in error for error in result.errors))

    def test_invalid_project_type_is_rejected(self) -> None:
        projects = self._load("projects.yaml")
        projects["projects"][0]["project_type"] = "commercial"
        self._save("projects.yaml", projects)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(any("project_type" in error for error in result.errors))

    def test_missing_required_field_is_rejected(self) -> None:
        projects = self._load("projects.yaml")
        del projects["projects"][0]["description"]
        self._save("projects.yaml", projects)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(any("description" in error for error in result.errors))

    def test_education_may_have_no_accomplishments(self) -> None:
        education = self._load("education.yaml")
        education["education"][0]["accomplishments"] = []
        self._save("education.yaml", education)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(result.is_valid, result.errors)

    def test_experience_requires_an_accomplishment(self) -> None:
        experiences = self._load("experiences.yaml")
        experiences["experiences"][0]["accomplishments"] = []
        self._save("experiences.yaml", experiences)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(
            any("must contain at least one item" in error for error in result.errors)
        )

    def test_record_technologies_missing_from_skills_are_warned(self) -> None:
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(result.is_valid, result.errors)
        self.assertEqual(len(result.warnings), 2, result.warnings)
        self.assertIn("'Docker'", result.warnings[0])
        self.assertIn("project_example_distributed_systems_lab", result.warnings[0])
        self.assertIn("'REST APIs'", result.warnings[1])

    def test_technology_warning_clears_when_skill_is_recorded(self) -> None:
        skills = self._load("skills.yaml")
        skills["skill_groups"][1]["skills"].append(
            {"id": "skill_example_docker", "name": "docker", "evidence_ids": []}
        )
        self._save("skills.yaml", skills)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(result.is_valid, result.errors)
        self.assertFalse(any("'Docker'" in warning for warning in result.warnings))

    def test_end_date_before_start_date_is_rejected(self) -> None:
        education = self._load("education.yaml")
        education["education"][0]["end_date"] = "2019-01"
        self._save("education.yaml", education)
        result = validate_candidate_directory(self.candidate_dir)
        self.assertTrue(any("must not precede" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
