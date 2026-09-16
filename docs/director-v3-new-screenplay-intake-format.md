# Director V3 新剧本 Intake 格式指南

这是空格式指南，不包含任何虚构人物、剧情或测试情节。实际源材料必须由用户明确
提供，并通过显式路径或 manifest 送入 Intake。

## 推荐格式：UTF-8 Plain Text / Markdown

```text
Title: <OPTIONAL_SOURCE_TITLE>
Language: <LANGUAGE>

Episode: <EPISODE_NUMBER>
Scene: <CANONICAL_SCENE_ORDINAL>
Location: <LOCATION>
Time: <TIME>
Characters: <CHARACTER_LIST>
Action:
<ACTION_TEXT>
Dialogue:
<DIALOGUE_TEXT>
```

字段是帮助解析和人工复核的结构提示，不是对内容的自动审批。可以有多个 Episode
和 Scene；不得为了满足数量而拆分真实场景。

## Manifest（粘贴文本）

```json
{
  "source_text": "<USER_PROVIDED_SOURCE_TEXT>",
  "source_origin": "USER_PASTED_TEXT",
  "user_provided": true,
  "source_title": "<OPTIONAL_SOURCE_TITLE>",
  "language": "<LANGUAGE>",
  "encoding": "utf-8"
}
```

## 可读取的文件

当前仓库已有附件解析器实际支持 `.txt`、`.md`、`.pdf`、`.docx`；Intake 还接受
`.markdown` 作为 Markdown 别名。PDF/DOCX 必须能提取到文本，否则会被
`SOURCE_TEXT_EXTRACTION_UNAVAILABLE` 拒绝。图像不是剧本源格式。

无论格式如何，`source_origin` 必须是用户提供的来源，且 `user_provided` 必须为
`true`。`FIXTURE`、`GOLDEN`、`SYNTHETIC`、`GENERATED_FOR_TEST` 和
`INTERNAL_SAMPLE` 永远不能进入生产 Fresh Intake。
