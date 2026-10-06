# PHASE_V7_5_PRODUCTION_EVIDENCE_SCOPE_RECONCILIATION_V7_5_1

**状态：`DIRECTOR_ATTEMPT4_PREFLIGHT_READY`**（未授权、未调用 Provider）。V7.5 历史结果保持 `FAILED CLOSED`，没有被改写。

## 逐项最终报告

1. **V7.5 最终状态**：`FAILED CLOSED`，历史证据 immutable。
2. **Attempt-3 是否永久 consumed**：是；原授权已消费，不能重用。
3. **Attempt-3 status**：`IR_INVALID`。
4. **Historical raw SHA**：`bc7af44934f4b3a0f9652fdaddc28b8cc67a24404c0bad6da7aa5170000fe7c5`。
5. **原 `PRODUCTION_DB_DELTA` 为什么错误**：BEFORE 是单 Packet/空下游的目标形状，AFTER 使用了未过滤的全库 inventory；两者没有同一 scope descriptor。
6. **BEFORE scope**：历史未声明 scope；观察到 Packet=1、其余目标快照=0。
7. **AFTER scope**：历史未声明 scope，实际为 global inventory（例如 Packet=63、Treatment=64、SceneBlocking=79）。
8. **是否确认 scope mismatch**：是，`DB_SNAPSHOT_SCOPE_MISMATCH_REPRODUCED`。
9. **是否保留原错误 artifact**：是，原 V7.5 `PRODUCTION_DB_*` 和 raw/report 未覆盖。
10. **新 target scope fingerprint**：`83fa9de56efb24c19e296be933cc5a394ddb7887e1356315642fd5c4be4ae80f`。
11. **Target DecisionPacket count**：`1`。
12. **Target DirectorTreatment count**：`0`。
13. **Target Authority count**：`0`。
14. **Target Pointer count**：`0`。
15. **Target SceneBlocking count**：`0`。
16. **Target ShotPlan / Storyboard / PromptIR / Media counts**：`0 / 0 / 0 / generation=0, candidate=0, official=0`。
17. **是否发现真实 target downstream write**：否；所有 target downstream counts 为 0。
18. **Source lineage 是否 byte-equivalent**：是；双次只读 refreeze 一致，source mutation count=0。
19. **Packet proposal 是否仍 awaiting_llm**：是，`{"decision":"awaiting_llm"}`。
20. **Attempt ledger 是否仍为 3**：是，`v7_3_attempt_1`、`v7_3_attempt_2`、`attempt-3`。
21. **下一 attempt**：`attempt-4`。
22. **`direction` 是否正式进入 ProposalIR contract**：是；Schema、runtime、compiler copy-only、offline test 均通过。
23. **是否存在 MiMo/raw SHA 特例**：否。
24. **Formal schema gate 是否进入 endpoint**：是，顺序为 `PARSE → IR_SCHEMA_VALIDATE → IR_VALIDATE → COMPILE`。
25. **scene_id 缺失是否 Provider=0**：是，HTTP 409 `SCENE_ID_REQUIRED`，Provider=0。
26. **future request 是否显式 `E01_SC001`**：是，attempt-4 preflight 固定显式 scene_id。
27. **advisory asset context 是否固定为空**：是，`ADVISORY_ASSET_CONTEXT=[]`。
28. **preflight request fingerprint**：`331223e1a5d7ee567a3b73091e35d00055212df6f5b57205043873819c951402`。
29. **endpoint request fingerprint**：`331223e1a5d7ee567a3b73091e35d00055212df6f5b57205043873819c951402`。
30. **两者是否完全一致**：是，共用 `build_source_grounded_director_execution_identity()`。
31. **当前 profile/model**：`local-llm-2vydoz` / `mimo-v2.5`，provider=`openai-compatible`，host=`https://api.xiaomimimo.com`。
32. **Provider calls**：0。
33. **Production writes**：0；Packet 64 本阶段未修改。
34. **Tests**：46 passed，0 failed（V7.5.1 scope、V7.2 execution、V7.4 IR、V7.4.1 integrity）。
35. **compileall**：PASS。
36. **diff check**：PASS。
37. **commit SHA**：runtime code/preflight base=`532b1ad8cc8e9776ab21495db670386bfc3aa231`。
38. **remote HEAD**：证据提交完成后复核并与本地 HEAD 一致。
39. **working tree**：证据提交并推送后应为 clean；最终命令复核。
40. **是否可以正式申请 attempt-4 新授权**：可以申请，但本阶段没有创建或消费授权；必须由用户提供新的明确 authorization_id 后才可执行真实 POST。

## Scope reconciliation

- [Mismatch audit](V7_5_DB_SNAPSHOT_SCOPE_MISMATCH_AUDIT.json) 明确禁止把历史 global AFTER 与 target BEFORE 相减。
- [Target current snapshot](TARGET_SCOPE_CURRENT_SNAPSHOT.json) 对每张表保存 scope mode、query predicates、lineage join path、count、row identity hash。
- [Reconciled delta](TARGET_SCOPE_RECONCILED_DELTA.json) 使用同一 scope fingerprint；Packet count=1，proposal unchanged，所有目标下游为 0。
- [Global inventory](GLOBAL_DB_INVENTORY.json) 明确 `inventory_only=true`，不参与 canary delta。

## Attempt-4 preflight

[ATTEMPT_4_PROVIDER_PREFLIGHT.json](ATTEMPT_4_PROVIDER_PREFLIGHT.json) 已冻结：Book 990453 / Episode 1 / Scene E01_SC001 / Script 64 / FactSnapshot 49 / ScriptIR 52 / Packet 64、attempt history=3、next=`attempt-4`、source units=12（11 action / 1 dialogue / 0 beat）、schema=`director_proposal_ir_v1`、Provider calls=0、authorization=`REQUIRED_NOT_GRANTED`。

V7.5.1 只完成证据 scope reconciliation 与 future preflight；没有执行真实 LLM、IMAGE、VIDEO、SHAPI、Poyo 或 75API。
