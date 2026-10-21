# Public examples

Every file in this directory is fictional and safe to publish. The examples
mirror the structure used by the local workflow without containing real
candidate or application data. See the repository's root `README.md` for the
complete setup and usage workflow.

To initialize a private working copy, copy the five YAML files from
`examples/candidate/` into `candidate/` and copy
`templates/resume.example.tex` to `templates/resume.tex`. Edit only the copies
with real information.

Job descriptions use the `<company>-<location>.txt` naming convention. Use the
job's city when one is given, otherwise use the country or `remote`. Separate
words with hyphens; for example,
`examples/inputs/example-company-example-city.txt` should be copied to
`inputs/example-company-example-city.txt`. When requesting a tailored resume,
identify the corresponding input file explicitly.

The working paths are ignored by Git. Do not force-add them.

Validate the fictional starter records with:

```text
python scripts/validate_candidate_data.py examples/candidate
```

`examples/output/` shows the resume and tailoring report the workflow produces
for the example job description. Check them with:

```text
python scripts/check_tailoring_output.py check examples/output/tailoring-report-example-company-example-city.json --candidate examples/candidate --template templates/resume.example.tex
```
