# 阶段九验收报告：模型管理入口上移与作用域整改

验收时间：2026-06-26 16:08  
结论：不通过。

## 本阶段预期

阶段九按此前确认的「阶段九前置」验收，不是验真实图片生成闭环，而是验模型管理信息架构整改：

1. 项目列表页应有全局「模型管理 / 模型设置」入口。
2. 不进入任何项目，也能打开模型管理。
3. 模型管理应从分镜生产画布里抽成可复用模块。
4. 内容准备页应能看到 LLM / 向量模型上下文，或至少有模型设置入口。
5. 分镜生产页可以保留快捷入口，但不能是唯一入口。
6. 模型管理仍需展示 LLM / 向量 / 图片 / 视频四类配置。

## 自动化结果

自动化通过，但不代表产品验收通过。

- `python -m py_compile api/model_registry.py api/server.py api/generation_adapters.py core/__init__.py core/vector_search.py`：通过。
- `python -m unittest tests.test_model_registry tests.test_generation_adapters -v`：11 tests passed。
- `npm run test`：8 files / 65 tests passed。
- `npm run build`：通过；仍有 Vite chunk size warning，非阻断。

## 浏览器验收结果

### 1. 项目列表全局模型管理入口

结果：不通过。

项目列表页没有「模型管理 / 模型设置 / 全局模型」入口。用户不进入项目，无法管理 LLM、向量、图片、视频模型。

证据：

- `01-project-list.png`
- `02-project-list-after-model-attempt.png`
- `browser-evidence.json`

关键结果：

```json
{
  "projectListHasModelEntry": false,
  "projectListOpenedModel": false,
  "projectListHasRegistryModal": false
}
```

### 2. 内容准备页模型上下文

结果：不通过。

内容准备页没有显示当前 LLM / 向量模型，也没有明显模型设置入口。  
这会让用户不知道剧本生成、小说解析、向量检索到底使用哪套模型。

证据：

- `04-content-prep.png`
- `browser-evidence.json`

关键结果：

```json
{
  "contentPrepHasModelContext": false
}
```

### 3. 分镜生产页模型管理入口

结果：通过，但它仍然是唯一入口。

分镜生产页能打开模型管理弹窗，且弹窗包含 LLM / 向量 / 图片 / 视频四类配置。

证据：

- `05-production.png`
- `06-project-model-registry.png`

关键结果：

```json
{
  "productionHasModelEntry": true,
  "projectInternalModelOpened": true,
  "hasFourCategoriesInModal": true
}
```

### 4. 模型管理组件抽离

结果：不通过。

静态扫描和源码确认：

- `ModelRegistryModal` 仍定义在 `web/src/prototyping/SceneComposer.tsx` 内部。
- `web/src/pages/ProjectsPage.tsx` 未接入模型管理。
- 没有发现独立的 `ModelRegistryModal.tsx` 或全局复用的模型管理组件。

这意味着模型管理仍然被分镜生产画布绑定，没有成为项目列表/项目级可复用配置。

### 5. 命名和乱码

结果：通过。

浏览器截图未发现旧主命名：

- `导演模式`
- `原型工作台`
- `高级编辑`
- `高级模式`

也未发现可见乱码。

关键结果：

```json
{
  "oldNamesVisible": false,
  "mojibakeVisible": false
}
```

## 主要问题

阶段九的核心目标是修正「模型管理入口只藏在无限画布里」这个 IA 错位。但当前实现没有完成这一点：

1. 项目列表没有全局模型管理入口。
2. 内容准备页没有模型设置入口或模型提示。
3. 模型管理弹窗仍在 `SceneComposer.tsx` 内部，没有抽离为可复用组件。
4. 用户仍必须先进入某个项目、再进入分镜生产，才能管理模型。

这和阶段九目标冲突。

## 建议修复任务

1. 在 `ProjectsPage.tsx` 右上角增加「模型管理」按钮。
2. 把 `ModelRegistryModal` 从 `SceneComposer.tsx` 拆出为独立组件，例如：

   ```text
   web/src/components/ModelRegistryModal.tsx
   web/src/services/modelRegistryClient.ts
   ```

3. `ProjectsPage`、`SceneComposer`、必要时 `ProductionMode` 共同复用同一个模型管理弹窗。
4. 内容准备页增加模型提示或入口，至少显示：

   - 当前 LLM
   - 当前向量模型
   - 「模型设置」按钮

5. 分镜生产页保留模型入口，但文案应是快捷入口，而不是唯一入口。
6. 增加前端测试覆盖：

   - 项目列表能打开模型管理。
   - 模型管理显示四类模型。
   - 保存后项目内读取同一套默认配置。

## 最终判断

阶段九不通过。

后端和既有模型管理能力没有坏，测试也通过；但本阶段最核心的产品信息架构整改没有完成。当前仍是「模型管理藏在分镜生产画布里」的旧结构。
