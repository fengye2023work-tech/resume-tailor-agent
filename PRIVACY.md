# Privacy policy for repository content

Never commit real candidate data to this repository.

Keep these items under the ignored `.resume-agent/` directory:

- Master Profiles and factual career records;
- approved Golden Record resumes and owner-edited HTML;
- company or job research;
- generated HTML, PDF, DOC, or DOCX files;
- wording preferences and edit-diff learning data;
- API keys, access tokens, cookies, and credentials.

Only fictional examples using `example.com`, fictional employers, and invented
experience may be committed as tests or documentation.

Before pushing, run:

```powershell
python -m resume_agent.privacy .
```

For an additional personal guardrail, create the ignored file
`.resume-agent/privacy-denylist.txt` with one private name, email, employer, or
project marker per line. The scanner checks tracked text against those terms
without adding them to the repository.
