# Event state lives in a JSON file committed to the repo

Between runs, canonical event state persists in a single JSON file
(`data/state.json`) that the scheduled workflow commits. Chosen over SQLite
(binary, not reviewable in PRs) and external stores (infrastructure,
secrets, new failure modes) because the state is small (~dozens of active
events), transparency matters more than query power, and a git history of
state changes is itself an audit log of what the agent believed and when.

Revisit if the file outgrows review (thousands of events) — SQLite is the
designated fallback.
