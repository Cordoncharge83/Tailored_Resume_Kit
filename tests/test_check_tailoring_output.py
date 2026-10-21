from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_tailoring_output import check_outputs, slugify  # noqa: E402


SUFFIX = "example-company-example-city"


class TailoringOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        shutil.copytree(ROOT / "examples", self.root / "examples")
        (self.root / "templates").mkdir()
        shutil.copy(ROOT / "templates" / "resume.example.tex", self.root / "templates")
        self.output_dir = self.root / "examples" / "output"
        self.report_path = self.output_dir / f"tailoring-report-{SUFFIX}.json"
        self.tex_path = self.output_dir / f"tailored-resume-{SUFFIX}.tex"
        self.template_path = self.root / "templates" / "resume.example.tex"

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _check(self):
        return check_outputs(
            self.report_path,
            self.root / "examples" / "candidate",
            self.template_path,
            self.root,
        )

    def _load_report(self) -> dict:
        return json.loads(self.report_path.read_text(encoding="utf-8"))

    def _save_report(self, report: dict) -> None:
        self.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def _replace_in_tex(self, old: str, new: str) -> None:
        text = self.tex_path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.tex_path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def _assert_error(self, fragment: str) -> None:
        result = self._check()
        self.assertTrue(any(fragment in error for error in result.errors), result.errors)

    def test_public_example_outputs_are_consistent(self) -> None:
        result = self._check()
        self.assertTrue(result.is_valid, result.errors)
        self.assertFalse(result.warnings, result.warnings)

    def test_slugify_follows_suffix_rules(self) -> None:
        self.assertEqual(slugify("Example Company, Inc."), "example-company-inc")
        self.assertEqual(slugify("Société Générale"), "societe-generale")
        self.assertEqual(slugify("  --Remote--  "), "remote")

    def test_missing_tailored_resume_is_rejected(self) -> None:
        self.tex_path.unlink()
        self._assert_error("matching tailored resume does not exist")

    def test_suffix_must_match_company_and_location(self) -> None:
        report = self._load_report()
        report["job"]["location"] = "Remote"
        self._save_report(report)
        self._assert_error("give suffix 'example-company-remote'")

    def test_modified_template_is_rejected(self) -> None:
        with self.template_path.open("a", encoding="utf-8") as handle:
            handle.write("% edited\n")
        self._assert_error("canonical template may have been modified")

    def test_template_line_endings_do_not_change_its_hash(self) -> None:
        text = self.template_path.read_bytes()
        self.template_path.write_bytes(text.replace(b"\n", b"\r\n"))
        result = self._check()
        self.assertTrue(result.is_valid, result.errors)

    def test_unknown_cited_id_is_rejected(self) -> None:
        report = self._load_report()
        report["profile"]["source_ids"].append("accomplishment_does_not_exist")
        self._save_report(report)
        self._assert_error("cites unknown candidate ID")

    def test_bullet_must_cite_its_own_record(self) -> None:
        report = self._load_report()
        report["bullets"][0]["source_ids"] = ["accomplishment_example_task_manager_api"]
        self._save_report(report)
        self._assert_error("is not 'experience_example_company_software_engineer_2024'")

    def test_every_record_must_be_selected_or_omitted(self) -> None:
        report = self._load_report()
        report["omitted_records"] = []
        self._save_report(report)
        self._assert_error("experience_example_community_lead_2023")

    def test_unmatched_requirement_must_not_cite_evidence(self) -> None:
        report = self._load_report()
        report["requirements"][2]["evidence_ids"] = ["accomplishment_example_company_api_delivery"]
        self._save_report(report)
        self._assert_error("must be empty for an unmatched requirement")

    def test_selected_skill_without_evidence_must_be_reported(self) -> None:
        report = self._load_report()
        report["unsupported_skills"] = []
        self._save_report(report)
        self._assert_error("must list 'skill_example_git'")

    def test_validator_warnings_must_be_copied_into_report(self) -> None:
        report = self._load_report()
        report["warnings"] = report["warnings"][1:]
        self._save_report(report)
        self._assert_error("must include the validator warning")

    def test_unreported_tex_bullet_is_rejected(self) -> None:
        self._replace_in_tex(
            "\\end{itemize}\n\n\\section*{Projects}",
            "\\item Led the migration to Kubernetes.\n\\end{itemize}\n\n\\section*{Projects}",
        )
        self._assert_error("is not recorded in report.bullets")

    def test_unbalanced_brace_is_rejected(self) -> None:
        self._replace_in_tex("\\textbf{Languages}:", "\\textbf{Languages:")
        self._assert_error("opening brace is never closed")

    def test_mismatched_environment_is_rejected(self) -> None:
        self._replace_in_tex("\\end{center}", "\\end{centre}")
        self._assert_error("\\end{centre} closes \\begin{center}")

    def test_unescaped_special_characters_are_rejected(self) -> None:
        self._replace_in_tex("Python, Java, TypeScript", "Python, C#, R&D, 50% coverage")
        result = self._check()
        for fragment in ("unescaped #", "unescaped &", "unescaped % after a number"):
            self.assertTrue(any(fragment in error for error in result.errors), result.errors)

    def test_alignment_ampersand_and_escaped_characters_are_allowed(self) -> None:
        self._replace_in_tex(
            "\\section*{Skills}",
            "\\section*{Skills}\n\\begin{tabular}{ll} C\\# & R\\&D, 50\\% \\end{tabular}",
        )
        result = self._check()
        self.assertTrue(result.is_valid, result.errors)

    def test_underscores_in_literal_arguments_are_allowed(self) -> None:
        self._replace_in_tex(
            "\\section*{Skills}",
            "\\section*{Skills}\\label{sec_skills}\n"
            "\\href{https://example.com/a_b#top}{Link} \\includegraphics[width=1cm]{photo_1}",
        )
        result = self._check()
        self.assertTrue(result.is_valid, result.errors)

    def test_unresolved_placeholder_is_rejected(self) -> None:
        self._replace_in_tex("\\section*{Skills}", "\\section*{Skills}\nTODO add skills")
        self._assert_error("unresolved placeholder 'TODO'")

    def test_changed_preamble_is_warned(self) -> None:
        self._replace_in_tex("margin=0.56in", "margin=0.4in")
        result = self._check()
        self.assertTrue(result.is_valid, result.errors)
        self.assertTrue(any("preamble differs" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
