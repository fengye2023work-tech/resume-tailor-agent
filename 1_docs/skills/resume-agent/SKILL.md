---
name: resume-agent
description: Use when tailoring a resume to a job description, researching hiring intent, selecting evidence, or generating a verified two-page HTML/PDF resume.
---

# Resume Agent

Use the current IDE session as the primary model and tool environment. Resume
Agent owns workflow state, business rules, artifact contracts, and acceptance
gates. Do not start `codex exec`, a nested model session, or a second agent loop.

Start with `resume-agent apply ... --host ide --json`. Execute the returned
action, write exactly the requested output file, then advance with
`resume-agent submit`. Use `resume-agent next`, `resume-agent resume`, and
`resume-agent status` to inspect or continue a run.

Research hiring intent before drafting. Select the nearest approved Golden
Record and make incremental changes rather than rewriting from zero. Use only
the matching private Master Profile, the selected Golden Record, current-run
artifacts, and applicable approved preferences.

Ask the user only when a missing fact materially affects truthfulness or
competitiveness. Strong framing is allowed when supported by real evidence.
Never invent employment, projects, ownership, tools, metrics, credentials, or
outcomes. Use established professional terminology; do not create abstract new
terms merely to sound technical.

After drafting, check facts and technical meaning before naturalizing the
language. Render exactly two pages and stop at owner review. Reusable learning
from manual edits requires explicit user approval; unapproved edits must not
become long-term preferences.

All personal data and generated artifacts stay under `.resume-agent/` and must
never be committed.
