# Resume Agent

Resume Agent is an IDE-first, CLI-managed workflow for researching a role,
selecting evidence, tailoring a two-page resume, and producing deterministic
HTML/PDF output.

## Privacy boundary

This public repository contains only reusable code, documentation, and fictional
examples. Real profiles, Golden Records, job research, wording preferences, and
generated resumes belong under `.resume-agent/`, which is ignored by Git.

Copy the fictional starter data before the first run:

```powershell
Copy-Item -Recurse examples/private-data/* .resume-agent/
python -m pip install -e 4_code
resume-agent doctor
```

Start an IDE-hosted application workflow:

```powershell
resume-agent apply --company "Example Labs" --role "AI Product Lead" `
  --language en --jd-file path/to/jd.txt --host ide --json
```

The current IDE session executes the returned action. Resume Agent keeps the
workflow state and validates every submitted artifact.

## Verification

```powershell
$env:PYTHONPATH=(Resolve-Path 4_code).Path
python -m unittest discover -s 4_code/tests -p "test_*.py" -v
python -m resume_agent.privacy .
```

See [PRIVACY.md](PRIVACY.md) before adding profiles, templates, or fixtures.
