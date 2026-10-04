# Autonomous Visual Asset Pipeline V1.2 Provider Failover Canary

- Status: AUTONOMOUS_SCENE_ASSET_PIPELINE_READY
- Scene: E01_SC002
- Previous v2 closure: CLOSED_MASTER_PROVIDER_CREDITS_INSUFFICIENT (1 attempt; derived=0; repair=0; VIDEO=0)

## Provider discovery and failover

- Eligible master/reference profiles: poyo-async/gpt-image-2, shapi-gemini-image/nano-banana-2, 75api-image/gpt-image-2-1k
- Master attempt 1: poyo-async / gpt-image-2 / CREDITS_INSUFFICIENT / task_created=false
- Failover triggered: yes; final master: shapi-gemini-image / nano-banana-2
- Master execution: 800c912780ab; SHA-256: 1a3dc3b2f8c69003f17dcaaba9e7374ae5f059a666b38156c7806c960011aa5f

## Derived views and evidence

- REVERSE: provider=shapi-gemini-image; execution=75e13c551377; reference_sha=1a3dc3b2f8c69003f17dcaaba9e7374ae5f059a666b38156c7806c960011aa5f; inline_reference=True
- SIDE: provider=shapi-gemini-image; execution=a031bbae4893; reference_sha=1a3dc3b2f8c69003f17dcaaba9e7374ae5f059a666b38156c7806c960011aa5f; inline_reference=True
- DETAIL: provider=shapi-gemini-image; execution=2dedc9fcdc4c; reference_sha=1a3dc3b2f8c69003f17dcaaba9e7374ae5f059a666b38156c7806c960011aa5f; inline_reference=True
- REVERSE: PASS; attempt=1; scores={'architecture_score': 92, 'landmark_score': 90, 'furniture_score': 88, 'lighting_score': 90}; critical=[]
- SIDE: PASS; attempt=1; scores={'architecture_score': 98, 'landmark_score': 97, 'furniture_score': 96, 'lighting_score': 97}; critical=[]
- DETAIL: PASS; attempt=1; scores={'architecture_score': 95, 'landmark_score': 92, 'furniture_score': 90, 'lighting_score': 88}; critical=[]

## Global Judge and authority

- Global Judge: PASS; same_physical_space=True
- Auto repair calls: 0
- SceneAuthority: READY

## Safety and budget

- Authorized IMAGE budget: 8; used: 5
- Real VIDEO calls: 0
- Production writes: 0; Book 990400 writes: 0; browser direct calls: 0; secret leaks: 0; orphan candidates: 0

## Verification

- Pairwise and global Judge evidence contain request/response fingerprints and 0-100 scores.
- All derived references use the locked master SHA and scene role.
- No keyframe or VIDEO generation was executed.
