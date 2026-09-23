# Candidate data validation contract

The executable validation contract lives in
`scripts/validate_candidate_data.py`. This document summarizes the public data
model; the script is authoritative when the documentation and implementation
disagree.

## Required files

Every candidate directory contains exactly:

- `profile.yaml`;
- `education.yaml`;
- `experiences.yaml`;
- `projects.yaml`;
- `skills.yaml`.

Duplicate YAML mapping keys and unexpected candidate YAML files are rejected.

## IDs and evidence

- Every `id` is globally unique across all five files.
- IDs start with a lowercase letter and contain only lowercase letters,
  digits, and underscores.
- Every `evidence_ids` value references an existing ID in the same candidate
  directory.
- Skill names are unique across all skill groups, ignoring case and surrounding
  whitespace.

## Required record fields

- Profile: `id`, `name`, `headline`, `summary`, `email`, and `links`.
- Profile link: `id`, `label`, and `url`.
- Language: `id`, `name`, and `proficiency`.
- Education: `id`, `institution`, `degree`, `field_of_study`, `location`,
  `start_date`, `end_date`, and `accomplishments`.
- Experience: `id`, `experience_type`, `role`, `start_date`, `end_date`, and
  `accomplishments`.
- Project: `id`, `name`, `description`, `project_type`, `technologies`, and
  `accomplishments`.
- Skill group: `id`, `name`, and `skills`.
- Skill: `id`, `name`, and `evidence_ids`.
- Accomplishment: `id` and `text`.

Professional and internship experiences require `employer`. Volunteering and
leadership experiences require `organization`.

## Allowed types

Experience types:

- `professional`;
- `internship`;
- `volunteering`;
- `leadership`.

Project types:

- `personal`;
- `academic`.

## Dates

Dates use `YYYY-MM`. An `end_date` may also be `present`. When both dates are
calendar dates, the end date cannot precede the start date.
