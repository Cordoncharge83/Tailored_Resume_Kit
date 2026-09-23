# Tailored Resume Kit

Tailored Resume Kit is a local, agent-assisted workflow for creating a
truthful LaTeX resume from structured candidate records and a supplied job
description. It works with Codex and Claude Code without a custom web
interface or direct LLM API integration.

The workflow selects and rewrites supported candidate evidence; it does not
invent missing experience. Each generated bullet is recorded in a separate
tailoring report with the candidate IDs that support it.

## What it does

- Stores candidate facts as structured YAML.
- Analyses a job description for responsibilities, qualifications,
  technologies, domain language, and useful keywords.
- Selects relevant experiences, projects, accomplishments, and skills.
- Generates a separate tailored `.tex` file from a canonical LaTeX layout.
- Generates a JSON report containing selection reasons, provenance,
  unmatched requirements, and warnings.
- Validates YAML structure, globally unique IDs, evidence references, required
  fields, dates, and allowed experience and project types.
- Keeps private candidate data, job descriptions, references, and generated
  outputs out of Git by default.

## What it does not do

- It does not provide a web application, hosted service, or SaaS product.
- It does not call an LLM through a custom API integration.
- It does not automatically compile PDFs.
- It does not automatically verify visual layout or one-page fit.
- It does not calculate or promise ATS-score improvements.
- It cannot support a requirement that is absent from the candidate records.

Generated LaTeX is compiled and visually reviewed manually, such as through
Overleaf.

## Requirements

- Codex or Claude Code, installed and authenticated.
- Python 3.10 or newer.
- A text editor for maintaining the private YAML records.
- A LaTeX environment such as Overleaf for manual compilation.

Install the pinned validation dependency with:

```text
python -m pip install -r requirements.txt
```

## Quick start

Clone the repository, then initialize private working files from the
publishable examples.

PowerShell:

```powershell
New-Item -ItemType Directory -Force candidate, inputs, output, references
Copy-Item examples\candidate\*.yaml candidate\
Copy-Item templates\resume.example.tex templates\resume.tex
Copy-Item examples\inputs\example-company-example-city.txt inputs\example-company-example-city.txt
```

macOS or Linux:

```bash
mkdir -p candidate inputs output references
cp examples/candidate/*.yaml candidate/
cp templates/resume.example.tex templates/resume.tex
cp examples/inputs/example-company-example-city.txt inputs/example-company-example-city.txt
```

Then:

1. Replace all fictional values under `candidate/` with factual candidate
   information while keeping every ID globally unique.
2. Replace the example content in `templates/resume.tex` with the desired
   canonical layout. Candidate claims still come only from the YAML records.
3. Add each real job description under `inputs/` using the
   `<company>-<location>.txt` naming convention.
4. From the repository root, ask Codex or Claude Code to tailor the resume to
   that specific input file.
5. Review both generated files, then compile the `.tex` file manually.

The initialized working paths are ignored by Git. Do not force-add them.

## Input naming

Name job-description files `<company>-<location>.txt`:

- Use the job's city when explicitly available.
- Otherwise use the country, or `remote` for a remote role.
- Convert words to lowercase filesystem-safe slugs separated by hyphens.

Examples include `example-company-example-city.txt` and
`example-company-remote.txt`.

When the repository contains multiple job descriptions, always identify the
target path in the request. For example:

```text
Tailor my resume to inputs/example-company-example-city.txt. Generate the
LaTeX resume and tailoring report, but do not modify my candidate records or
canonical template.
```

## Using Codex and Claude Code

Both agents use the same workflow instructions:

- Codex reads `AGENTS.md`.
- Claude Code reads `CLAUDE.md`, which imports `AGENTS.md`.

Keep shared workflow changes in `AGENTS.md`; do not duplicate them in
`CLAUDE.md`. Start the chosen agent from the repository root and provide the
job-description path in the request.

## Expected outputs

For an input representing Example Company in Example City, the agent creates:

```text
output/tailored-resume-example-company-example-city.tex
output/tailoring-report-example-company-example-city.json
```

The JSON report records:

- extracted job requirements and keywords;
- selected and omitted records with reasons;
- every generated bullet and its supporting candidate IDs;
- unmatched requirements and unsupported skill-list entries;
- warnings and ambiguities;
- confirmation that the canonical template was not modified.

## Repository layout

```text
AGENTS.md                         Shared workflow for coding agents
CLAUDE.md                         Claude Code import of AGENTS.md
.github/workflows/validate.yml    Public-data validation in CI
examples/candidate/               Fictional, publishable YAML records
examples/inputs/                  Fictional, publishable job description
schemas/README.md                 Candidate-data validation contract
scripts/                          Deterministic validation and privacy checks
templates/resume.example.tex      Fictional, publishable LaTeX template
tests/                            Safeguard regression tests
candidate/                        Private candidate records; ignored
inputs/                           Private job descriptions; ignored
templates/resume.tex              Private canonical template; ignored
output/                           Generated resumes and reports; ignored
references/                       Private source documents; ignored
```

## Data model and traceability

Candidate YAML is the sole source of candidate facts. Records and atomic
accomplishments use stable, globally unique IDs. Skills may list
`evidence_ids` that point to accomplishments demonstrating those skills.

The agent may reword or combine compatible facts from the same record, but it
must never create unsupported technologies, metrics, responsibilities,
deployment status, project maturity, dates, or authority. See `AGENTS.md` for
the complete rules.

## Deterministic safeguards

Validate the public fictional data:

```text
python scripts/validate_candidate_data.py examples/candidate
```

Validate a private working candidate without publishing it:

```text
python scripts/validate_candidate_data.py candidate
```

Check that private paths remain ignored and scan publishable text for
high-confidence secrets and non-fictional example contact data:

```text
python scripts/check_public_tree.py
```

Run all regression tests:

```text
python -m unittest discover -s tests -v
```

The validator rejects unsafe YAML construction, duplicate mapping keys,
missing required files or fields, invalid dates, duplicate or malformed IDs,
unresolved evidence references, duplicate skill names, and unsupported
experience or project types. GitHub Actions runs the same public checks on
pushes and pull requests. Private ignored candidate data is never uploaded to
CI.

Automated scanning reduces accidental disclosure risk but cannot prove that a
file contains no personal information or secrets. Review the complete Git
diff and publishable file list before every public release.

## Privacy

The committed examples are fictional. Real candidate records, job
descriptions, references, canonical resumes, generated resumes, and reports
are ignored. Before publishing a branch, inspect the files Git will include
and never force-add an ignored private path.

Git ignore rules do not remove secrets or personal data from existing commit
history. If private data was previously committed, remove it from history
before publishing.

## Current limitations

Generation is performed interactively by the selected coding agent. The
repository does not include PDF compilation, visual page-fit checks, or
automated ATS scoring.

## Contributing

See `CONTRIBUTING.md` before submitting changes. Contributions must use only
fictional example data and must keep the shared agent workflow in `AGENTS.md`.

## License

Tailored Resume Kit is available under the MIT License. See `LICENSE`.
