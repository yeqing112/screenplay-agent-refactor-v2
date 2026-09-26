# Task Runtime Audit

## 已存在的任务与状态

- TaskRun（models/task.py，migration d4e5f6a7b8c9）：task id/kind/status/progress/payload/error/timestamps。
- Creative task（api/server.py 的 _creative_tasks、_enqueue_creative_task）：image/reference-image/video queued/running/completed/failed。
- Pipeline task：/api/pipeline/task/{task_id}、run_script_pipeline、run_storyboard。
- Prompt compile task：/api/storyboard-prompt-compile-tasks/{task_id}。
- Generation execution：GenerationExecutionRecord。
- Retry attempt：StoryboardVideoRetryAttempt，保存 immutable input snapshot 并要求人工确认。

## 判断

异步主要由 FastAPI BackgroundTasks、asyncio.to_thread、provider polling 的 asyncio.sleep 构成。当前代码没有证明独立 Redis/Rabbit/SQS queue、worker process、scheduler、lease/visibility timeout 或 dead-letter queue。

- 异步任务：有。
- 状态管理：有，但来源分裂；TaskRun 可持久化，creative 运行细节仍在进程内字典。
- 重试：有；provider/transport、scene retry、视频人工确认 retry 并非一套 policy。
- 执行记录：有；canonical execution record 和 retry attempt。
- 调度系统：未确认。
- 跨进程恢复：未确认。

## 风险

多 worker 可能重复执行或覆盖状态；queued/running 不一定代表 provider 可继续查询；超时、网络中断、进程崩溃后的 reconcile 依赖局部逻辑；TaskRun 通用 payload 不能替代 immutable generation request snapshot；legacy 与 canonical 可能形成双重事实源。

## 最小目标

建立 GenerationOrchestrator 持久化状态机：claim/lease、submit、poll、reconcile、terminal transition、idempotency 和 retry policy。TaskRun 继续承载上层 pipeline，但不代替 GenerationExecution；若暂不引入外部 queue，至少把 worker claim 和恢复语义落到数据库。

