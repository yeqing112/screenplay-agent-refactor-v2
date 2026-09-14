# Director Quality V2.4.2b — Final Report

## Findings and implementation

旧 Canary 的单一 `edit` 样本来自历史 `tail_repair.root_causes` selector，而非 Frozen B2 数据本身。改用 authoritative `rank_tail_root_causes_v2()` 后，真实 evidence 可提供 `edit`、`emotion`、`information`、`performance` 四类；`camera` 没有足够 camera-specific evidence，列为 missing，未伪造。

新增 deterministic root-cause scoped context resolver 后，4/4 选中样本的首轮 request 均具备非空 `relevant_beats`、`relevant_shots` 与 `allowed_plan_shot_ids`，且 shot ID 均来自 structural candidate。Provider boundary 现在通过 sanitizer 移除 `attempt_kind`、`previous_raw_output`、`previous_validation_errors` 等 legacy 顶层字段；base、attempt、provider 三层 fingerprint 均可审计。

## Real MiMo result

- model：`mimo-v2.5`
- sample_count：4
- repair types：edit / emotion / information / performance
- First Pass：edit 1/1、emotion 0/1、information 1/1、performance 0/1；aggregate **2/4（50%）**
- Final IR：**2/4（50%）**
- FORMAT_REPAIR：2 次尝试，0 次成功
- Canonical Compile：2/2（100% of final-valid）
- Candidate Contract Pass：2/2
- Fact Override Accepted：0
- Request Echo：0
- Unknown Provider Shape：0
- fingerprint：6/6 非空
- semantic attempts：6
- provider HTTP requests：6
- transport retries：0
- parser retries：0

失败原因是 MiMo 对 `emotion`/`performance` 样本返回了严格 IR 不合规字段；Validator 保持严格，未放宽 schema、未绕过 canonical 编译、未重跑更大 Pilot。

## Final status

`PROTOCOL_CANARY_FAILED`。覆盖率本身已达 FULL_TYPE_COVERAGE，但 First Pass 低于 80%、Final IR 低于 100%，因此不满足 `READY_FOR_TARGETED_TAIL_REEVALUATION`。本轮已按规则 STOP。

## Evidence

- Provider-free gate：`artifacts/director-quality-v2-4-2b-provider-free-preflight.json`
- Manifest：`artifacts/director-quality-v2-4-2b-protocol-canary-manifest.json`
- Real result：`artifacts/director-quality-v2-4-2b-protocol-canary-20260914T155655Z.json`
- Detailed protocol report：`artifacts/director-quality-v2-4-2b-protocol-canary-report.md`
- Gap audit：`artifacts/director-quality-v2-4-2b-gap-audit.md`

所有 production/storyboard/media/image/video/object_storage/production_shadow 副作用均为 0；未处理 CI，未清理或覆盖历史产物。
