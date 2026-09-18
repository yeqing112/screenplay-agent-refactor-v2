# Historical Migration Replay Fix

`bf85be21e043` is now a static Alembic DDL baseline; it no longer imports current ORM metadata.
`f05ab1af29bc` is additive and copies legacy `episode_outlines.content` into `raw_content` without dropping the old column.
The revision identities and lineage are unchanged. Databases already stamped past these revisions are not re-executed; the fix is verified only with disposable fresh and legacy fixtures.
