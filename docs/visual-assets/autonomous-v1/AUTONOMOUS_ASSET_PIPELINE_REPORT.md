# Autonomous Visual Asset Pipeline V1 Report

- Status: `AUTONOMOUS_SCENE_ASSET_PIPELINE_READY`
- Scene: `E01_SC002`
- Manual approvals required: `0`
- Manual view selection: `0`
- IMAGE profile: `local-image-mw4y52` / `shapi-gemini-image` / `nano-banana-2`
- Derived route: `REFERENCE_IMAGE_DERIVATION`
- Visual judge: `VISION_JUDGE_EXECUTED`

## Generation

- Master calls: `1`
- Reverse calls: `2`
- Side calls: `2`
- Detail calls: `1`
- Repair calls: `2`
- Total IMAGE calls: `6`
- Real VIDEO calls: `0`

## Geometry authority

- window: LEFT wall
- sink: LEFT wall, directly below window
- door: REAR_RIGHT zone
- table: CENTER_FOREGROUND
- cabinet: BACK wall
- Geometry is authoritative; the Master image is its visual implementation.

## Consistency

- `REVERSE`: `PASS`; architecture=90, landmarks=90, furniture=90, lighting=90; critical=[]
- `SIDE`: `PASS`; architecture=90, landmarks=90, furniture=90, lighting=90; critical=[]
- `DETAIL`: `PASS`; architecture=90, landmarks=90, furniture=90, lighting=90; critical=[]

## Automatic repair

- Views repaired: `['REVERSE', 'SIDE']`
- Attempts: `[{'view_id': 'REVERSE', 'attempt': 2, 'kind': 'REPAIRING', 'call': 5, 'route': 'REFERENCE_IMAGE_DERIVATION', 'corrections': ['保持 dining_table', '保持 rear_right_kitchen_door', '保持 left_window_edge', '不得改变 SceneGeometryIR 的门窗水槽餐桌橱柜拓扑']}, {'view_id': 'SIDE', 'attempt': 2, 'kind': 'REPAIRING', 'call': 6, 'route': 'REFERENCE_IMAGE_DERIVATION', 'corrections': ['保持 dining_table', '保持 sink_below_window', '保持 back_cabinet', '不得改变 SceneGeometryIR 的门窗水槽餐桌橱柜拓扑']}]`
- No human approval or view selection was requested during the run.

The prior 2×2 generated scene is retained as `scene-v0-failed-baseline.jpg`; it is not Scene Authority.

## Media fingerprints

- `MASTER`: `93c740cf2913152147e97c5604264a0224149f778356d73aa1d672e0e52ddd0e`
- `REVERSE`: `1117275b4927ed89397401160e6f4c2ee36ec4ad79c64484f1d24bffdd999815`
- `SIDE`: `b2c9a8ebc3564ad598fb999063bebc3fed60e5c593921a7a4efcde4987a712b9`
- `DETAIL`: `509979115d00d76a8ee87a7e3fa0d0b303e5c381bc0dbb1d76a2d1aa12d8bd9b`
