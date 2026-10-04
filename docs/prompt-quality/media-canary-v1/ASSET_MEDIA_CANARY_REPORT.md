# Asset Media Canary V1 Report

## Status

`ASSET_MEDIA_CANARY_PENDING_HUMAN_REVIEW`

This package contains exactly five real IMAGE candidates. No candidate was approved, promoted, or bound to production media. VIDEO calls were not made.

## IMAGE provider

- Profile: `local-image-mw4y52`
- Provider: `shapi-openai-images`
- Model: `grok-imagine-image-quality`
- Base URL: `https://shapi.vip/v1`
- Preflight: `READY`
- Credential: resolved by the isolated runtime; no secret is written to this package.

## Candidate outputs

### 林晚
- Execution: `3e824e66d464`
- Candidate: `CANDIDATE`
- File: `01-linwan.jpg` (1024×1024, 199819 bytes)
- Prompt fingerprint: `a0926744f9d46025c3d01c0f0d739ff8403e8254bb3f4b583978da98795f5128`
- Visual review: `PENDING_HUMAN_VISUAL_REVIEW`

### 陆叔
- Execution: `73bb4689b3be`
- Candidate: `CANDIDATE`
- File: `02-lushu.jpg` (1024×1024, 238378 bytes)
- Prompt fingerprint: `eb0733a24e35e214d3a5355e28819f4a6c6e097d5332896c4ce62da00a223032`
- Visual review: `PENDING_HUMAN_VISUAL_REVIEW`

### E01_SC002 出租公寓厨房
- Execution: `7df02bc743eb`
- Candidate: `CANDIDATE`
- File: `03-kitchen.jpg` (1024×1024, 332751 bytes)
- Prompt fingerprint: `f37b6912e7f8839bf5a36c6f06b825c2fc8e7f3ff8be444de3b069340cd9da8a`
- Visual review: `PENDING_HUMAN_VISUAL_REVIEW`

### APPLE 苹果
- Execution: `6990392a9063`
- Candidate: `CANDIDATE`
- File: `04-apple.jpg` (1024×1024, 202769 bytes)
- Prompt fingerprint: `40dda263e8a6b2c824c0bf3e896510e9d0e19bdf9629b17fe95da4041f234d01`
- Visual review: `PENDING_HUMAN_VISUAL_REVIEW`

### HANDBAG 手提包
- Execution: `37f5efae72a4`
- Candidate: `CANDIDATE`
- File: `05-handbag.jpg` (1024×1024, 176586 bytes)
- Prompt fingerprint: `097f0efc4a4ae14e4fa9448c0d33516885b7b0a88942071147ed03057c7362f7`
- Visual review: `PENDING_HUMAN_VISUAL_REVIEW`

## Safety and scope

- Real IMAGE calls: `5` (normal budget max `5`; reserve `0`).
- Real VIDEO calls: `0`.
- Browser direct provider calls: `0`.
- Production DB writes: `0`.
- Book 990400 writes: `0`.
- Orphan rows: `0` in the isolated canary database.
- Automatic visual quality scoring: `not used`.

## Human review checklist

- 林晚 / 陆叔：六视图身份、脸型、发型、服装、配饰和身体比例是否一致。
- 出租公寓厨房：四视图建筑结构、餐桌、厨房门、窗户、固定家具和灯光方向是否连续。
- APPLE：形状、颜色、材质、尺寸比例是否稳定。
- HANDBAG：包型、提手、扣件、材质、颜色和多视角识别是否稳定。

下一步只有在人工确认资产稳定后，才进入 3 张关键帧 → 3 个真实 VIDEO；本轮不生成关键帧、不调用 VIDEO。
