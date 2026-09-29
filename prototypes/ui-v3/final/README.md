# Final Hybrid V3 Prototype

Final Hybrid V3 将三套已确认方向合并为一个候选生产 UI：

- A：Global Shell、Dashboard Hero、媒体优先的 Main Canvas、Asset Library
- C：Shot Navigator 密度、Scene grouping、Review Inbox 三栏、生产状态 Pipeline
- B：剧本与导演 Editorial reading、Director Intent、AI Why 的局部 serif

## Local preview

从仓库根目录启动静态服务器，例如：

```text
python -m http.server 4177
```

然后访问 `http://127.0.0.1:4177/prototypes/ui-v3/final/`。

## Prototype-only behavior

- 5 个一级页面：制片台、剧本与导演、镜头工坊、资产库、交付。
- Shot Studio：42 Shot fixture、Scene grouping、搜索、Episode / Scene / State filter、100 Shot stress toggle、Keyframe / Image / Video / Official stage、展开详情、Context collapse。
- Review Inbox：Keyframe / Image / Video / Director 四种审核，20 item stress contract、空队列预览、连续批准和下一条切换。
- 快捷键：A 批准、R 要求修改、Space 预览、↑↓ 审核项、←→ 阶段；在输入、选择器和 drawer 中禁用危险快捷键。
- 所有操作只改变浏览器内存；backend calls、database writes、provider calls 均为 0。
