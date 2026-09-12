# Golden Project fixtures

These fixtures are deterministic, ID-free regression inputs.  Each directory
contains `project.json`, `script.json`, `assets.json`, and `expected.json`.
The production regression runner seeds them into a fresh SQLite database and
uses the stable `golden_key` rather than a database auto-increment id.

Real provider calls are intentionally excluded from Required CI.  Provider
gray tests belong to the separate nightly/manual workflow.
