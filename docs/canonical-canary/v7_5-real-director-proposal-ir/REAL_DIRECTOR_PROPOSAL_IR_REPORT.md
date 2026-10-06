# PHASE_DIRECTOR_LLM_PROPOSAL_IR_REAL_CANARY_V7_5 最终审计报告

**结论：`DIRECTOR_PROPOSAL_IR_READY_FOR_REVIEW` 未达成。本轮 FAILED CLOSED，禁止 retry / confirm。**

## 逐项交付（对应授权文本第 44 节）

1. **Base HEAD**：`c16b0d66a89fb5af84f426aba9bc7fcc9693b7ed`（执行前冻结）。
2. **Authorization ID**：`v7_5-director-proposal-ir-real-canary-authorization-3`。
3. **Attempt ID**：`attempt-3`。
4. **历史 attempt count before**：2。
5. **Request fingerprint**：实际 `a151a26c6e5514d6657e24362906ea3638d8cfff20366493fc5ee2a60527f8f9`；冻结预期 `26b0a52fd64508d33482be227459a5892039e0924ab96ec9c2eab2375ed77d93`，**不匹配**。
6. **SourceAuthoringUnit fingerprint**：`2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f`。
7. **Profile / model**：`local-llm-2vydoz` / `mimo-v2.5`。
8. **Provider POST count**：1 次到 Provider；另有 1 次本地 `SCENE_ID_REQUIRED` 拒绝。
9. **Transport attempts**：1。
10. **Retry count**：0。
11. **HTTP status**：Provider 200；应用最终返回 502 `DIRECTOR_PROPOSAL_IR_INVALID`。
12. **Provider request ID**：空（Provider 未返回）。
13. **Raw response SHA**：`bc7af44934f4b3a0f9652fdaddc28b8cc67a24404c0bad6da7aa5170000fe7c5`。
14. **是否与前两次 SHA 相同**：否；前两次均为 `9a4792265b52e9f42c91c925f296d3ef110649c4318edf614ff7f439ef6b3566`。
15. **Raw forensic 是否 parse 前 commit**：是，`persisted_before_parse=true`。
16. **Attempt ledger 最终数量**：3。
17. **Attempt-3 terminal status**：`IR_INVALID`。
18. **JSON parse**：PASS，调用一次。
19. **Formal schema**：FAIL；两个 `character_directions` 含未允许字段 `direction`。
20. **Runtime validation**：BLOCKED；两条 `DIRECTOR_PROPOSAL_IR_CHARACTER_DIRECTION_FIELD_UNEXPECTED`。
21. **Creative beat 数量**：6（取证响应）。
22. **每个 beat source refs**：Beat 1: SAU_E01_SC001_001, SAU_E01_SC001_002；Beat 2: SAU_E01_SC001_003, SAU_E01_SC001_004；Beat 3: SAU_E01_SC001_005；Beat 4: SAU_E01_SC001_006, SAU_E01_SC001_007, SAU_E01_SC001_008；Beat 5: SAU_E01_SC001_009, SAU_E01_SC001_010；Beat 6: SAU_E01_SC001_011, SAU_E01_SC001_012。
23. **12/12 coverage**：PASS，12/12。
24. **Passthrough 数量**：0。
25. **Compiler 状态**：`NOT_RUN`。
26. **Compiler 新增 creative semantics 数量**：0（编译边界未到达）。
27. **Candidate status 是否 PROPOSED**：否；未生成 candidate，Packet proposal 仍为 `{"decision":"awaiting_llm"}`。
28. **Scene objective**：取证响应描述为在封闭、潮湿空间中围绕不确定的童年线索与指令逐层加压；未获 canonical authority。
29. **Dramatic question**：取证响应围绕“胶片来自谁、谁在操控这场安排、顾沉是否知道更多”展开；未获 canonical authority。
30. **Director scene label**：Provider 返回了 E01_SC001 的场景标签；因 Schema/Runtime 失败，仅作 forensic。
31. **Hook 数量**：4 个。
32. **Hook 对应 beat**：2, 4, 5, 6。
33. **“也许是你自己”所属 beat**：Beat 4，refs 包含 `SAU_E01_SC001_008`。
34. **该对白 performance interpretation**：顾沉保持表面平静，通过停顿、视线和短促回答制造不确定性；没有把动机说死。该分析仅为 forensic reading。
35. **是否存在 source 过度解读**：未发现已 canonize 的 source 过度解读；unknowns/prohibited interpretations 被保留，且未进入 authority。
36. **是否新增角色**：Runtime 未报 participant invalid；未发现新增 declared participant。由于未编译，不授予 canonical 结论。
37. **Source mutation count**：0。
38. **Creative authority invalid count**：0（Authority 未创建；不是“已通过”）。
39. **DecisionPacket 64 是否更新**：是，仅更新 `model_info` 的 raw forensic / provider audit / attempt ledger / failure report；proposal 未替换。
40. **DirectorTreatment writes**：0。
41. **Authority / Pointer writes**：0 / 0。
42. **SceneBlocking writes**：0。
43. **IMAGE / VIDEO**：0 / 0。
44. **Production DB exact delta**：目标下游表行数全部 `+0`；Packet 64 仅有取证元数据变化，详见 `PRODUCTION_DB_DELTA.json`。
45. **是否建议 confirm ProposalIR**：不建议；当前没有可确认的 ProposalIR candidate。
46. **最大质量风险**：Provider 输出契约与 flat v1 Schema 不一致；其次是冻结预检与正式 endpoint 的 prompt evidence 不同构。
47. **Tests / compileall / diff**：38 个定向测试通过；`python -m compileall -q api core models` 通过；`git diff --check` 通过。
48. **Working tree**：clean。
49. **Commit SHA**：`072e39aedb3961d99c5debcdce2d336f415f882a`。
50. **Remote HEAD**：`072e39aedb3961d99c5debcdce2d336f415f882a`，与本地一致。

## 中文导演质量取证（非 canonical review）

- **核心导演理解**：响应尝试把空间湿度、物件残留、人物反应和外部声音组织成逐级加压的悬念链。
- **信息递进**：空间氛围 → 海鸥别针/母亲标签与烧焦胶片 → 童年相片疑点 → “也许是你自己”反问 → 铜铃与湿鞋的即时威胁 → 车票指令和下一场出口，结构上可读。
- **道具功能**：海鸥别针承载身份疑点；烧焦胶片承载被破坏的信息；铜铃负责声音转折；湿鞋把未知来者转成外部威胁；车票提供时间、地点、要求和下一场钩子。
- **表演边界**：顾沉的动机、林晚童年真相、门外人物身份和塞车票者身份仍应保持 ambiguity。响应列出 unknowns 与 prohibited interpretations，未将其写入 authority。
- **合同合法但导演水平较低的问题**：本次不能进入该质量判定，因为合同先在 Schema/Runtime 阶段失败；仅能保留为后续人工审查事项。

## 失败原因与下一步门禁

本次不是成功的 ProposalIR review。实际 fingerprint `a151a26c6e5514d6657e24362906ea3638d8cfff20366493fc5ee2a60527f8f9` 与冻结 fingerprint `26b0a52fd64508d33482be227459a5892039e0924ab96ec9c2eab2375ed77d93` 不同；正式 raw 的 `character_directions` 使用 `direction` 而不是 v1 允许的 `objective / obstacle / strategy / performance_notes`。依授权不得修复、不得 retry、不得 confirm。下一轮必须先完成代码级契约对齐，并重新获得新的明确外部调用授权。
