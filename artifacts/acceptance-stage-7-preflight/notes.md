# 阶段七前置验收报告

验收时间：2026-06-26 09:53  
结论：通过。

## 验收范围

阶段七前置主要验收四件事：

1. 当前运行态是否已加载阶段七模型管理修复。
2. 模式命名是否统一为「内容准备 / 分镜生产 / 高级编排」。
3. 新项目或空项目是否默认进入内容准备。
4. 已有项目是否能从内容准备顺畅进入分镜生产，高级编排是否退到次级入口。

## 自动化结果

- `python -m py_compile api/model_registry.py api/server.py api/generation_adapters.py core/llm.py`：通过。
- `python -m unittest tests.test_model_registry -v`：5 tests passed。
- `npm run test`：8 files / 64 tests passed。
- `npm run build`：通过；仍有 Vite chunk size warning，非阻断。

## 运行态模型管理修复

结果：通过。

当前 `4173 -> 8765` 运行态已经加载最新阶段七修复。通过 API 尝试把真实视频模型设为默认时，后端会回退到 Mock 视频模型。

证据：`api-live-8765.json`

关键结果：

```json
{
  "requestedVideoDefault": "stage7-preflight-real-video",
  "resolvedVideoDefault": "builtin-mock-video",
  "resolvedVideoProvider": "prototype-task-adapter",
  "pass": true
}
```

## 命名与入口

结果：通过。

静态扫描和浏览器截图都确认主入口已统一：

- `内容准备`
- `分镜生产`
- `高级编排`

未在主流程截图里发现旧主标签：

- `导演模式`
- `原型工作台`
- `高级编辑`
- `高级模式`

证据：

- `02-existing-default.png`
- `03-content-prep.png`
- `04-storyboard-production.png`
- `05-advanced-orchestration.png`
- `browser-evidence.json`

## 新项目默认路径

结果：通过。

点击项目列表左侧「新建项目」卡片后，默认进入「内容准备」。页面提示当前是空项目，建议先上传文件或粘贴小说内容，再一键生成完整剧本。

证据：

- `08-new-project-clicked.png`
- `new-project-evidence.json`

关键验证：

```json
{
  "hasContentPrep": true,
  "hasStoryboardProduction": true,
  "hasAdvanced": true,
  "hasEmptyProjectGuidance": true,
  "hasOldLabels": false,
  "hasMojibake": false
}
```

## 已有项目默认路径

结果：通过。

打开已有项目「神农架历险记」时，项目已具备剧本、分镜图、视频和成片序列，因此默认进入「分镜生产」。这符合「已有完整生产资料的项目可以直接进入分镜生产」的规则。

证据：`02-existing-default.png`

## 内容准备链路

结果：通过。

内容准备页可见：

- 剧本生产区
- 上传文件 / 粘贴文本 / 使用当前项目文本
- 项目名称
- 集数、每集时长、改编方向
- 一键生成完整剧本
- 底部流程：小说解析 → 逐章分析 → 世界观 Bible → 人物画像 → 改编方案 → 分集大纲 → 剧本写作 → 质检 → 分镜生成
- 右上角「进入分镜生产」

证据：`03-content-prep.png`

## 分镜生产链路

结果：通过。

分镜生产页可见：

- 顶部阶段标签「分镜生产」
- 内容准备 / 分镜生产 / 高级编排三段切换
- 镜头、参考资产、图片版本、视频版本、成片序列
- 引用线和生产关系
- 模型管理入口
- 检查本集、失败任务、问题清单、导出前检查

证据：`04-storyboard-production.png`

## 高级编排

结果：通过。

「高级编排」作为顶部次级入口保留，能点击进入，不再作为普通用户默认路径。

证据：`05-advanced-orchestration.png`

## UX / 可访问性观察

1. 主路径清晰度：通过  
   新用户从「内容准备」开始，已有项目可直接进入「分镜生产」，符合短剧生产流程。

2. 命名一致性：通过  
   主流程未发现旧命名混杂。

3. 截图可见范围内的可读性：基本通过  
   深色界面对比度整体可用；小号标签较多，但不影响本阶段验收。

4. 截图无法完全验证项：  
   文件上传、长文本粘贴后的完整生成链路没有在本轮执行真实 LLM 生产，只验收了入口、状态、命名、默认路径和模型管理运行态。

## 最终判断

阶段七前置通过，可以进入下一阶段。

建议下一步开始做真实模型接入前的 provider adapter 设计：先定义统一的图片/视频 provider adapter 接口、错误码、任务状态映射、费用/限流字段，再接第一个真实图片模型。
