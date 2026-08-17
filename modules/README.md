# 短剧工业化流水线 — 模块设计 v1

## 架构概览

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  模块1   │ →  │  模块2   │ →  │  模块3   │ →  │  模块4   │ →  │  模块5   │ →  │  模块6   │
│  剧本层   │    │  分镜层   │    │  资产层   │    │  生成层   │    │  音频层   │    │  合成层   │
│          │    │          │    │          │    │          │    │          │    │          │
│ 文本输入  │    │ 文本→结构 │    │ 文本→图片  │    │ 图片→视频  │    │ 语音+音效 │    │ 视频+字幕 │
│          │    │          │    │          │    │          │    │  +BGM   │    │  →成片   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     ↓               ↓               ↓               ↓               ↓               ↓
  reader        storyboard      asset_factory    generator       audio_factory   compositor
  bible          (待建)                          (视频API调用)    (TTS+音效+BGM)  (剪映/PR/
  portrait                                                                       Remotion)
  script
  scene_setup
```

## 模块间接口定义

### 模块1 → 模块2（剧本层 → 分镜层）

**模块1 产出清单**（已有）：
- `outputs/{title}/visual/时代妆造规范.md` — era_spec
- `outputs/{title}/visual/道具提示词.md` — props（JSON + MD）
- `outputs/{title}/visual/场景提示词.md` — locations（JSON + MD）
- `outputs/{title}/makeups/第XX集定妆照.md` — makeup
- `outputs/{title}/scripts/第XX集剧本.md` — script

**模块2 输入协议**：（从模块1产出中提取）
- scene 名 + visual_prompt → 来自 `场景提示词.json`
- prop 名 + visual_prompt → 来自 `道具提示词.json`
- character name + 定妆照 prompt → 来自 `第XX集定妆照.md`
- script 内容 + 角色动作 → 来自 `第XX集剧本.md`

**模块2 输出 → 模块3 + 4 + 5**：见下方"分镜表 JSON Schema"

---

### 模块2：分镜表 JSON Schema

**文件路径**：`outputs/{title}/storyboard/第{XX}集分镜.json`

```jsonc
{
  "$schema": "storyboard-v1",
  "meta": {
    "title": "string (小说标题)",
    "episode": "int (集号)",
    "episode_title": "string (本集标题)",
    "genre": "string (赛道)",
    "era": "string (时代规范)",
    "total_duration_sec": "int (本集总时长)",
    "total_shots": "int (总镜头数)"
  },
  "shots": [
    {
      "shot_id": "E01S01 (格式: E{集号}S{镜号})",
      "duration_sec": "int (单镜头时长，3-8秒)",
      "sequence": "int (镜头序号)",

      // 镜头语言
      "frame": "远近全中近特写",
      "camera": "固定/推/拉/摇/移/跟/升降",
      "transition": "硬切/淡入淡出/闪白/模糊过渡",

      // 画面内容
      "scene": "string (场景名，对应模块3资产key)",
      "characters": [
        {
          "name": "string (角色名)",
          "action": "string (动作描述)",
          "expression": "string (表情)",
          "position": "string (画面位置)"
        }
      ],
      "props": ["string (道具名列表)"],

      "visual_prompt_zh": "string (中文视觉提示词，供可灵/辰入梦)",
      "visual_prompt_en": "string (英文视觉提示词，供MJ/Runway)",

      // 关键帧（模块3产出的描述/占位）
      "keyframes": [
        {
          "type": "keyframe",
          "description": "string (关键帧内容描述)",
          "asset_path": "string|null (模块3回填)",
          "seed": "int|null (模块3回填)"
        }
      ],

      // 音频
      "dialogue": "string (台词/旁白)",
      "sound_effects": ["string (音效列表)"],
      "bgm_mood": "string (BGM情绪)",

      // 资产引用（模块3回填）
      "assets": {
        "scene_ref": "string|null (场景图路径)",
        "character_refs": {
          "角色名": "string|null (角色图路径)"
        },
        "props_refs": {
          "道具名": "string|null (道具图路径)"
        }
      },

      // 生成参数（模块3/4回填）
      "generation": {
        "method": "图生视频/文生视频",
        "keyframe_image": "string|null (关键帧图路径)",
        "motion": "静态/微动/中动/大动",
        "seed": "int|null",
        "model": "string|null (使用的模型)"
      }
    }
  ]
}
```

---

### 模块2 → 模块3（分镜层 → 资产层）

**传递数据**：完整分镜表（含 shot_id / scene / characters / props / visual_prompt / keyframes[].description）

**模块3 职责**：
1. 遍历分镜表 shots，为每镜生成关键帧图
2. 为每个场景生成参考图（wide / close_up / 多角度）
3. 为每个角色生成定妆图（portrait / full_body）
4. 为每个道具生成参考图
5. 回填 asset_path / seed / prompt 到分镜表

**资产目录结构**：

```
assets/{title}/
├── keyframes/
│   ├── E01S01/
│   │   └── kf_001.jpg
│   ├── E01S02/
│   │   └── kf_001.jpg
│   └── ...
├── characters/
│   ├── 母亲/
│   │   ├── portrait.jpg
│   │   ├── full_body.jpg
│   │   └── prompt.txt         # 生成的原始 prompt + seed
│   └── ...
├── scenes/
│   ├── 二蛋家卧室/
│   │   ├── wide.jpg
│   │   ├── close_up.jpg
│   │   └── prompt.txt
│   └── ...
└── props/
    └── 煤油灯/
        └── ref.jpg
```

---

### 模块3 → 模块4（资产层 → 生成层）

**传递数据**：已回填资产引用的分镜表

**模块3 输出扩展**：每个 shot 的 `assets` 和 `generation` 字段非空

**模块4 职责**：
1. 分镜表驱动：遍历 shots
2. 取 `generation.keyframe_image` 作为图生视频首帧
3. 取 `visual_prompt_zh/en` 构造动态 prompt
4. 调用视频生成 API（Seedance/可灵/Runway/辰入梦）
5. 产出视频片段，存到 `outputs/{title}/clips/{shot_id}.mp4`
6. 回填 `generation.seed` + `generation.model` 到分镜表

---

### 模块4 → 模块5 + 6（生成层 → 音频层 + 合成层）

**传递数据**：完整分镜表 + 视频片段路径 + 各镜头元数据

**模块5 职责**：
1. 按 shots 生成对话（TTS / ElevenLabs / 豆包）
2. 按 `sound_effects` 匹配音效
3. 按 `bgm_mood` 生成/匹配 BGM
4. 输出音频轨道到 `outputs/{title}/audio/`

**模块6 职责**：
1. 按 shot 顺序拼接视频片段
2. 叠加音频轨道（人声 + 音效 + BGM）
3. 加字幕（基于 dialogue 字段）
4. 加包装（片头/片尾/过渡特效）
5. 质检（角色一致性 / 音画同步 / 字幕校对）
6. 输出成片 `outputs/{title}/成品/第{XX}集.mp4`

---

## 当前项目状态（模块1）

```
✅ reader       — 逐章分析，产出角色表
✅ bible        — 小说圣经，含人物/情节/世界观
✅ portrait     — 人物画像，含身份/属性/别名归并
✅ script       — 剧本生成（每集）
✅ scene_setup  — 时代规范/场景/道具/定妆照
⬜ storyboard  — 分镜工程（待建）
⬜ asset_factory — 资产生成（待建）
⬜ generator     — 视频生成（待建）
⬜ audio_factory — 音频生成（待建）
⬜ compositor    — 剪辑合成（待建）
```

---

## 边界条件与设计原则

1. **模块2输出是整条产线的骨架**，一张完整的分镜表驱动所有下游模块。模块2质量直接决定成片质量，理应投入最多的 prompt 工程
2. **模块3/4/5可以并行**，因为它们依赖的数据是同一个分镜表的不同字段
3. **模块6是串行终点**，必须等前序模块全部完成才能启动
4. **每个模块的输出文件路径固定**，后续模块通过约定路径读取，不依赖内存传递
5. **资产回填**：模块3生成的图路径写入分镜表，模块4读取该路径后使用。回填机制确保分镜表始终是"可复现的完整记录"
6. **LLM 文本→图片的转换损耗**是主要质量风险。模块1产出的自然语言 scene/makeup prompt 在模块3被翻译成具体图片时会产生偏差，需要通过 prompt 工程和 seed 固定来控制
