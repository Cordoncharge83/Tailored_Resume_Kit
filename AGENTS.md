# Resume Tailoring Workflow

## Purpose and scope

This repository provides a local, agent-assisted workflow for producing a
truthful LaTeX resume tailored to a supplied job description. It does not
include a custom web interface, hosted service, or direct LLM API integration.

Follow these instructions for resume-generation requests. Do not modify
candidate records or the canonical template unless the user explicitly asks
for those source files to be changed.

## Private inputs

The initialized private workspace contains:

- `candidate/profile.yaml`;
- `candidate/experiences.yaml`;
- `candidate/projects.yaml`;
- `candidate/education.yaml`;
- `candidate/skills.yaml`;
- `templates/resume.tex`;
- one or more job descriptions under `inputs/`.

Job descriptions use `<company>-<location>.txt`. Use a lowercase,
filesystem-safe slug, with the city when explicitly available, otherwise the
country or `remote`.

Use the job-description path explicitly named by the user. If no path is
named and exactly one `.txt` job description exists under `inputs/`, use it.
If multiple job-description files exist, ask which file to use; do not guess
based on filename order or modification time.

## Deterministic preflight

Before generating a resume, run:

```text
python scripts/validate_candidate_data.py candidate
```

If validation fails, do not generate a resume from invalid or ambiguous data.
Report the validation errors and wait for the user to correct the source, or
modify candidate data only when the user explicitly asks for that change.
Never silently repair IDs, evidence references, types, dates, or required
fields.

Validation warnings do not block generation. Never resolve a warning by
adding a skill or other candidate fact yourself; copy each warning into the
tailoring report's warnings.

Then record the canonical template's fingerprint as the report's
`canonical_template.sha256_before`:

```text
python scripts/check_tailoring_output.py template-hash
```

## Candidate facts and truthfulness

- Treat the YAML files under `candidate/` as the only authorized source of
  candidate facts.
- Treat prose and bullets already present in `templates/resume.tex` only as
  layout and density examples, not as evidence.
- If the template conflicts with candidate YAML, use the YAML fact and record
  the conflict as a warning.
- If candidate data does not support a job requirement, omit it or report it
  as unmatched.
- Never invent technologies, metrics, responsibilities, impact, deployment,
  scale, ownership, dates, duration, certifications, or other candidate facts.
- Never exaggerate project maturity or authority. Do not transform an
  academic project, personal project, internship, prototype, volunteering,
  leadership experience, or historical deployment into another category.
- Preserve the meaning and scope of every supporting record when rewriting.

## Team contributions and historical facts

- For team records, `team_size` describes the team, `role_focus` describes the
  candidate's own contribution, and `other_team_contributions_included` lists
  work done by other team members.
- Never present an item from `other_team_contributions_included` as the
  candidate's own work, in bullets, the profile, or skills. Do not use it to
  satisfy a job requirement; report that requirement as unmatched instead.
- A team record's `technologies` describe the project as a whole. Attribute a
  technology to the candidate personally only when a cited accomplishment
  supports it.
- Treat `historical: true` as a past fact. Do not present it as current,
  ongoing, still deployed, or still valid, and do not remove the context that
  makes it historical.

## Stable IDs and evidence

- Every record and atomic accomplishment must retain its stable ID.
- Every generated bullet must cite one or more existing candidate IDs in the
  tailoring report.
- Prefer skills with accomplishment evidence over unsupported skill-list
  entries.
- A skill with no evidence reference may be selected only when it exists in
  `candidate/skills.yaml`; list it in the report as unsupported by an
  accomplishment.
- Never create or silently repair source IDs during resume generation.

## Template usage

- `templates/resume.tex` is the canonical private LaTeX template.
- Never modify it during resume generation.
- Copy its content to the required output path, then tailor the copy.
- Preserve its preamble, packages, commands, margins, typography, hyperlink
  configuration, section styling, and overall structure.
- Do not redesign, simplify, or reformat it unless explicitly requested.
- Prefer omitting lower-relevance content over shrinking fonts, margins, or
  spacing.
- Escape LaTeX-sensitive characters correctly.
- The user compiles and reviews generated LaTeX manually, such as in Overleaf.

## Fixed factual content

The following are not job-tailorable and must remain consistent with the
candidate YAML:

- name and contact information;
- employers and organizations;
- role titles, experience types, dates, and locations;
- education institution, degree, field, and dates;
- project names and factual project types.

Entries may be omitted for relevance or space, but their factual identity or
category must not change.

## Tailorable content

The agent may tailor:

- the profile summary;
- which supported accomplishments appear;
- accomplishment wording and ordering;
- which experiences and projects appear and their ordering;
- skill selection, grouping, and ordering;
- whether optional leadership or education accomplishments appear.

## Job-description analysis

Before writing the resume:

1. Read the selected job-description file.
2. Extract the employer, role, location, seniority, responsibilities, required
   qualifications, preferred qualifications, technologies, domain language,
   and important keywords.
3. Separate genuine role requirements from generic company language.
4. Rank candidate records using relevance and demonstrated evidence, not
   simple keyword frequency.
5. Prioritize required qualifications over preferred qualifications.
6. Do not force irrelevant keywords into the resume.
7. Record ambiguities instead of resolving them with invented assumptions.

## Content generation

- Generate concise, achievement-oriented bullets.
- Use job-description terminology only when it accurately describes the
  candidate's recorded work.
- A bullet may combine compatible facts from the same record.
- Do not combine unrelated facts in a way that creates a new claim.
- Preserve important supported accomplishments even if the job description
  uses different wording.
- Avoid keyword stuffing and awkward repetition.
- Preserve approximately the canonical template's content density.

## Section behavior

- Keep the canonical template's section order unless explicitly requested
  otherwise.
- Generate a role-relevant Profile using only supported claims.
- Select and order Experience entries by relevance while preserving their
  factual type and chronology where appropriate.
- Select Projects by relevance while preserving personal or academic type.
- Keep education identity and dates fixed; select optional bullets for
  relevance.
- Retain or omit Leadership according to relevance and available space.
- Include only recorded candidate skills and prioritize relevant ones. The
  Skills section may list only entries from `candidate/skills.yaml`; a
  technology that appears only in a record's `technologies` list does not add
  a Skills entry. Report it as an unmatched requirement or warning instead.

## Required outputs

For every resume-generation request, create both:

- `output/tailored-resume-<company>-<location>.tex`;
- `output/tailoring-report-<company>-<location>.json`.

Build the suffix from the hiring company and application location. Use the
city when explicitly available, otherwise the country or `remote`. Convert
both values to lowercase ASCII filesystem-safe slugs, replace punctuation or
spaces with single hyphens, and remove leading or trailing hyphens. If the
company or location cannot be identified confidently, ask before generating.

For example, an Example Company application in Example City produces:

- `output/tailored-resume-example-company-example-city.tex`;
- `output/tailoring-report-example-company-example-city.json`.

The report must include:

- the source job-description path;
- extracted requirements and keywords;
- selected experiences and projects with selection reasons;
- omitted projects with brief omission reasons;
- every generated bullet and its source candidate IDs;
- unmatched requirements;
- selected skills lacking accomplishment evidence;
- warnings and ambiguities;
- confirmation that the canonical template was not modified.

Write the report in the version 1 format described in
`schemas/tailoring-report.md`. `examples/output/` contains a complete example.

## Final checks

Before finishing, run `template-hash` again, record the result as
`canonical_template.sha256_after`, and then run:

```text
python scripts/check_tailoring_output.py check output/tailoring-report-<company>-<location>.json
```

The checker confirms that the candidate data validates, the canonical template
is unchanged, both output files exist with the same suffix, every cited ID
exists and fits its field, every `\item` is recorded in the report, and that
braces, environments, placeholders, and LaTeX-sensitive characters are clean.
If it fails, fix only the generated outputs and run it again. Never edit
candidate data or the canonical template to make it pass. Pass any checker
warnings on to the user.

The checker cannot judge meaning, so also confirm that:

- no candidate claim came solely from the template or job description;
- every bullet preserves the meaning and scope of its cited records;
- unsupported requirements are reported honestly.

Do not generate a PDF or attempt local LaTeX compilation. Do not claim that
the resume compiles, fits on one page, or improves an ATS score. If the user
provides Overleaf compilation or layout feedback, revise only the generated
LaTeX unless they explicitly request a canonical-template change.

For public-release or contribution tasks, also run:

```text
python scripts/validate_candidate_data.py examples/candidate
python scripts/check_tailoring_output.py check examples/output/tailoring-report-example-company-example-city.json --candidate examples/candidate --template templates/resume.example.tex
python scripts/check_public_tree.py
python -m unittest discover -s tests -v
```
