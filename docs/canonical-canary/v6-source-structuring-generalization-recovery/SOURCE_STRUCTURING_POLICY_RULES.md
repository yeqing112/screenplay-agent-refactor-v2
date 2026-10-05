# Source Structuring Policy Rules

The production source path is provider free and source authoritative. It may
only verify or recover provenance that is already present in the candidate.

## Allowed deterministic rules

- exact equality and exact substring evidence verification;
- local character offsets and UTF-8 byte offsets;
- SHA-256 hashes and source fingerprints;
- source span ordering and textual distance;
- quote delimiter validation within a unique utterance context;
- schema validation and structural scene ID generation;
- explicit caller policy constraints;
- ambiguity detection and fail-closed results;
- evidence-preserving dialogue demotion;
- evidence pointer recovery when the nearest candidate is unique.

## Forbidden without semantic authority

- proper-name-specific branches;
- target-dialogue-specific branches;
- chapter-specific branches;
- keyword lists used as semantic classification;
- inferred locations or scene names;
- inferred props, characters, speaker changes, or dramatic meaning;
- dialogue promotion or action paraphrase.

`display_name` is presentation metadata. `source_identity_evidence` is the
source fact. An unresolved location remains empty with authority
`UNRESOLVED` until a later authorized semantic stage supplies it.
