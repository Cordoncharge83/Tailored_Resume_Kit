# Tailoring report format

Every resume-generation request produces
`output/tailoring-report-<company>-<location>.json` next to
`output/tailored-resume-<company>-<location>.tex`. This document describes
report version 1. The executable contract lives in
`scripts/check_tailoring_output.py`; the script is authoritative when the
documentation and implementation disagree.

`examples/output/` contains a complete example built from the fictional
candidate records and job description.

## Top-level fields

All fields are required and no other fields are allowed.

| Field | Type | Contents |
| --- | --- | --- |
| `report_version` | integer | Always `1`. |
| `job_description_path` | string | Repository-relative path of the job description used. |
| `job` | object | `company`, `location`, and `role` strings; `seniority` string or `null` when not stated. |
| `canonical_template` | object | `path` of the canonical template, and its `sha256_before` and `sha256_after` fingerprints. |
| `requirements` | list | Every extracted responsibility and qualification, with its match status. |
| `keywords` | list of strings | Important job-description keywords. |
| `selected_records` | list | Experience, project, and education records used, each with `id` and `reason`. |
| `omitted_records` | list | Records left out, each with `id` and `reason`. |
| `profile` | object | Generated profile `latex` and its `source_ids`. |
| `bullets` | list | Every generated `\item`, with `record_id`, `latex`, and `source_ids`. |
| `selected_skills` | list of skill IDs | Skills shown in the resume. |
| `unsupported_skills` | list of skill IDs | Selected skills whose `evidence_ids` is empty. |
| `warnings` | list of strings | Every candidate-validator warning, verbatim, plus any other warnings. |
| `ambiguities` | list of strings | Unresolved ambiguities in the job description or candidate data. |

## Requirements

Each requirement has:

- `text`: the requirement as stated or closely paraphrased;
- `category`: `responsibility`, `required`, or `preferred`;
- `status`: `matched`, `partial`, or `unmatched`;
- `evidence_ids`: accomplishment, experience, project, education, or
  certification IDs; empty for `unmatched` and non-empty otherwise;
- `note` (optional): why a match is partial, or why apparent evidence was not
  used.

Unmatched requirements are the requirements whose status is `unmatched`.

## Template fingerprint

Run `python scripts/check_tailoring_output.py template-hash` before generation
and record the output as `sha256_before`, then run it again at the end and
record `sha256_after`. Both must equal the template's current fingerprint.
Line endings are normalized before hashing, so a CRLF/LF conversion alone does
not count as a modification.

## Checks

`python scripts/check_tailoring_output.py check <report>` fails when:

- the report or tailored resume is missing, or their suffixes differ;
- the suffix does not match the slugs of `job.company` and `job.location`;
- the report has missing, unexpected, or wrongly typed fields;
- the candidate data fails validation, or a validator warning is missing from
  `warnings`;
- a cited ID does not exist, or has the wrong kind for its field;
- a bullet cites anything other than its own record or that record's
  accomplishments, or belongs to a record that is not selected;
- an experience, project, or education record is neither selected nor
  omitted, or is listed twice;
- `unsupported_skills` does not exactly cover the selected skills without
  evidence;
- either template fingerprint differs from the current template;
- an `\item` in the resume is missing from `bullets`, a bullet is missing from
  the resume, or the profile text does not appear in it;
- braces or `\begin`/`\end` environments are unbalanced;
- the document body contains unresolved placeholders, an unescaped `&`
  outside alignment environments, an unescaped `#` or `_`, or a `%` directly
  after a number.

It warns when the resume preamble differs from the canonical template or the
job-description file name does not match the output suffix.

The checker cannot judge whether wording is truthful, whether a bullet keeps
the meaning of its sources, or how the resume renders. Those still need the
agent's and the user's review.
