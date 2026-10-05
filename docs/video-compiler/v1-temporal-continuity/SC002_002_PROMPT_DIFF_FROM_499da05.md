# SC002_002 Prompt Diff From `499da05`

- Old SHA: `c87f2d638cfc21aa5601f9a4b475d16641bff659dcc0c1891ae67134e63c47cb`
- New SHA: `bd2a0e5e5fa6daefe880a6f1468596b6c58dd6700d4483d6d3e6cb0ff743cb60`
- Old word count: `1873`
- New word count: `1793`
- Word count delta: `-80`

## Closure changes

- Union boundaries are scheduling metadata only; source performance beats emit once.
- Source camera beats emit once and carry their own realism modifiers.
- Dialogue windows retain exact source start/end times.
- Listener reaction projection uses three meaningful events and one reaction-delay phrase.
- Terminal hold is emitted once with no dialogue, primary action, prop interaction or camera event.
