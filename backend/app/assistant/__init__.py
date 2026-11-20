"""The Otto assistant (phase 6a): what the right-hand panel shows beside a page of an assessment.

It is rule-based, behind `CopilotEngine` (engine.py). Everything in this package reads: the assessment's records, in
the words the pages' own views already give them. Nothing here decides, runs, accepts or changes anything, and a read
never asks Claude.

A decision or a start made in the panel is not made here. On Confirm the browser sends the very request the page's own
button sends (for a suggestion: `POST /api/plans/{plan}/otto/proposals/{proposal}/{decision}`), so the same code path,
the same record and the same refusals apply as on the page. `backend/tests/assistant/` holds the tests of these rules.
"""
