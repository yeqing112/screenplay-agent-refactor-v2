# Autonomous Visual Asset Pipeline V1 Report

- Status: `ASSET_CONSISTENCY_GENERATION_FAILED`
- Scene: `E01_SC002`
- Manual approvals required: `0`
- Manual view selection: `0`
- Derived route: `GEOMETRY_CONSTRAINED_TEXT_DERIVATION`
- Visual judge: `VISION_JUDGE_EXECUTED`

## Generation

- Master calls: `1`
- Reverse calls: `3`
- Side calls: `2`
- Detail calls: `1`
- Repair calls: `2`
- Total IMAGE calls: `7`
- Real VIDEO calls: `0`

## Geometry

- window: LEFT wall
- sink: LEFT wall, directly below window
- door: REAR_RIGHT zone
- table: CENTER_FOREGROUND
- cabinet: BACK wall
- Geometry IR is topology authority; the Master image is its visual implementation.

## Consistency

- `REVERSE`: `REPAIR`; architecture=2, landmarks=2, furniture=3, lighting=4; critical=['Upper cabinets are split into two separate units with a tall narrow cabinet between them, instead of the continuous 5-door run in MASTER', 'Doorway is positioned on the back wall to the right of the cabinets, whereas MASTER places the doorway on the right side wall', 'No continuous tiled backsplash behind the counter; tiles only appear in a small section near the sink']
- `SIDE`: `REPAIR`; architecture=3, landmarks=3, furniture=2, lighting=4; critical=['Sink changes from white farmhouse (MASTER) to stainless steel inset (SIDE).', 'Doorway in SIDE shows a green door with glass panel and hallway rug; MASTER doorway shows open room with sofa.', 'Upper cabinets in SIDE are 4 doors with different wear patterns vs 5 doors in MASTER.']
- `DETAIL`: `REPAIR`; architecture=2, landmarks=2, furniture=2, lighting=3; critical=['Window topology mismatch: MASTER has a large double-pane window with a central vertical mullion; DETAIL shows a single-pane window with no mullion.', 'Sink placement mismatch: MASTER sink is positioned under the window; DETAIL sink is positioned to the right of the window on a perpendicular counter run.']

## Automatic repair

- Views repaired: `['REVERSE', 'SIDE']`
- Repair attempts: `2`
- No human approval or view selection was requested.

The old 2×2 generated scene is retained as `scene-v0-failed-baseline.jpg`; it is not Scene Authority.
