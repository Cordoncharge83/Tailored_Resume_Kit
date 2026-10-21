# Contributing

Thank you for helping improve Tailored Resume Kit.

## Privacy first

- Never commit real candidate records, resumes, job applications, contact
  details, references, or generated outputs.
- Use only fictional data under `examples/` and reserved `example.com` URLs.
- Do not force-add paths ignored by `.gitignore`.
- Inspect the complete Git diff and publishable file list before opening a
  pull request.

## Workflow changes

- Keep shared Codex and Claude Code instructions in `AGENTS.md`.
- Keep `CLAUDE.md` as the single `@AGENTS.md` import unless a documented
  Claude-specific instruction becomes necessary.
- Keep candidate facts separate from template prose.
- Preserve stable IDs and evidence references in example data.
- Keep PDF compilation optional and local, and never commit downloaded tools
  or generated PDFs.
- Do not add claims of visual layout validation or ATS improvement unless
  those capabilities are implemented and verified.

## Scope

Prefer small changes with clear documentation. If a change affects the YAML
model, update all relevant fictional examples and, once deterministic
validation is available, its schemas and tests.

Do not include generated resumes, tailoring reports, LaTeX build artifacts,
or local agent settings in a contribution.

## Required checks

Install the pinned dependency and run all safeguards before submitting a
change:

```text
python -m pip install -r requirements.txt
python scripts/validate_candidate_data.py examples/candidate
python scripts/check_tailoring_output.py check examples/output/tailoring-report-example-company-example-city.json --candidate examples/candidate --template templates/resume.example.tex
python scripts/check_public_tree.py
python -m unittest discover -s tests -v
```

CI repeats these checks using only publishable fictional data.
