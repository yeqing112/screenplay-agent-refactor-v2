# Director Runtime V1.0 — M0 Release Foundation 验收记录

日期：2026-09-10  
范围：确定性回归基础设施、测试隔离、运行时配置与 Required CI

## 变更

1. `tests/test_storyboard_decision_evidence.py` 不再依赖历史 `book_id=990309`，测试内动态创建并清理项目和镜头。
2. pytest 默认使用临时 SQLite、上传目录和 Chroma 目录；测试会释放 SQLAlchemy engine 后再清理临时目录。
3. 新增 5 个 Golden Project 夹具及 `scripts/run-golden-regression.py`，覆盖对白权力变化、悬疑揭示、动作阻挡、多人物调度、道具连续性。
4. `check:production` 改为全量 Python 测试、Golden 回归、配置检查和前端构建；历史真实项目审计不再作为 Required gate。
5. 正式默认端口统一为 API `18765`、Web `5175`；隔离 E2E 通过 `E2E_API_URL`/`E2E_WEB_URL` 覆盖。

## 已验证

```text
python scripts/run-golden-regression.py
5 fixtures / 5 passed / 0 failed

npm run config:verify
OK — formal API 18765 / Web 5175
```

全量 `npm run check:production` 已通过：后端 `560 passed`、Golden `5/5`、配置检查通过、前端 `tsc + vite build` 成功。收费模型、图片/视频供应商不会被 Required CI 调用。

## 后续

- 在 CI 环境完成一次完整门禁并保存摘要。
- 增加手动/nightly 真实模型灰度 workflow，明确确认、费用上限、失败重试和回放。
- M0 绿灯后进入 M1 `DirectorTreatment`：独立的数据模型、迁移、证据包和只读预览，不并入 `AgentPlan`。
