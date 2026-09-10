# Book 75 机器提示词导出只读预览

- 模式：readonly_machine_prompt_export_preview
- 目标模型：minimax-h3
- 分镜数：26
- API 提交：False（本预览只导出，不提交）
- 参考图总数：54
- H3 integrated 描述最短长度：783
- 导出模式：minimax-h3 webui_copy, generic-zh-video webui_copy

## 分镜逐条预览

### E1-S1｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：中景，固定机位，时长约 3 秒。
起始：林小夏倚在收银台后，眼皮耷拉，指尖缓慢敲击台面，目光偶尔快速瞥向监控屏幕。
过程：林小夏维持慵懒姿态，眼神看似涣散
落点：承接拆分镜头 2：她打哈欠，说话
光影：惨白荧光灯，从头顶直射，制造生硬阴影。货架商品标签反光刺眼。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 1] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏倚在收银台后，眼皮耷拉，指尖缓慢敲击台面，目光偶尔快速瞥向监控屏幕. Observable action timeline: 0.00-0.80s: 林小夏倚在收银台后，眼皮耷拉，指尖缓慢敲击台面，目光偶尔快速瞥向监控屏幕。 Camera: 固定机位. 0.80-3.00s: 林小夏维持慵懒姿态，眼神看似涣散 Camera: 固定机位. 3.00-4.00s: 承接拆分镜头 2，她打哈欠，说话 Camera: 固定机位. Final frame: 承接拆分镜头 2，她打哈欠，说话. Shot size: 中景; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 1｜便利店收银台｜3 秒｜16:9
首帧：林小夏倚在收银台后，眼皮耷拉，指尖缓慢敲击台面，目光偶尔快速瞥向监控屏幕。
镜头：中景，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：林小夏倚在收银台后，眼皮耷拉，指尖缓慢敲击台面，目光偶尔快速瞥向监控屏幕。
- 1.05-2.40s：林小夏维持慵懒姿态，眼神看似涣散
- 2.40-3.00s：承接拆分镜头 2，她打哈欠，说话
结束落点：承接拆分镜头 2，她打哈欠，说话
连续性约束：人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S2｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：中景，固定机位，时长约 3 秒。
起始：承接拆分镜头 2：她打哈欠，说话
过程：她打哈欠，说话
落点：承接拆分镜头 3：目光扫向空无一人的街道
光影：惨白荧光灯，从头顶直射，制造生硬阴影。货架商品标签反光刺眼。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 2] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 2，她打哈欠，说话. Observable action timeline: 0.00-0.80s: 承接拆分镜头 2，她打哈欠，说话 Camera: 固定机位. 0.80-3.00s: 她打哈欠，说话 Camera: 固定机位. 3.00-4.00s: 承接拆分镜头 3，目光扫向空无一人的街道 Camera: 固定机位. Final frame: 承接拆分镜头 3，目光扫向空无一人的街道. Shot size: 中景; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 2｜便利店收银台｜3 秒｜16:9
首帧：承接拆分镜头 2，她打哈欠，说话
镜头：中景，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：承接拆分镜头 2，她打哈欠，说话
- 1.05-2.40s：她打哈欠，说话
- 2.40-3.00s：承接拆分镜头 3，目光扫向空无一人的街道
结束落点：承接拆分镜头 3，目光扫向空无一人的街道
连续性约束：开头承接上一镜结束状态：承接拆分镜头 2：她打哈欠，说话。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S3｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：中景，固定机位，时长约 3 秒。
起始：承接拆分镜头 3：目光扫向空无一人的街道
过程：目光扫向空无一人的街道
落点：承接拆分镜头 2：突然，风铃声响起。她身体几不可查地一僵
光影：惨白荧光灯，从头顶直射，制造生硬阴影。货架商品标签反光刺眼。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 3] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 3，目光扫向空无一人的街道. Observable action timeline: 0.00-0.80s: 承接拆分镜头 3，目光扫向空无一人的街道 Camera: 固定机位. 0.80-3.00s: 目光扫向空无一人的街道 Camera: 固定机位. 3.00-4.00s: 承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵 Camera: 固定机位. Final frame: 承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵. Shot size: 中景; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 3｜便利店收银台｜3 秒｜16:9
首帧：承接拆分镜头 3，目光扫向空无一人的街道
镜头：中景，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：承接拆分镜头 3，目光扫向空无一人的街道
- 1.05-2.40s：目光扫向空无一人的街道
- 2.40-3.00s：承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵
结束落点：承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵
连续性约束：开头承接上一镜结束状态：承接拆分镜头 3：目光扫向空无一人的街道。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S4｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：中景，固定机位，时长约 3 秒。
起始：承接拆分镜头 2：突然，风铃声响起。她身体几不可查地一僵
过程：突然，风铃声响起。她身体几不可查地一僵
落点：承接拆分镜头 2：突然，风铃声响起。她身体几不可查地一僵
光影：惨白荧光灯，从头顶直射，制造生硬阴影。货架商品标签反光刺眼。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 4] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵. Observable action timeline: 0.00-0.80s: 承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵 Camera: 固定机位. 0.80-3.00s: 突然，风铃声响起。她身体几不可查地一僵 Camera: 固定机位. 3.00-4.00s: 承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵 Camera: 固定机位. Final frame: 承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵. Shot size: 中景; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 4｜便利店收银台｜3 秒｜16:9
首帧：承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵
镜头：中景，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵
- 1.05-2.40s：突然，风铃声响起。她身体几不可查地一僵
- 2.40-3.00s：承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵
结束落点：承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵
连续性约束：开头承接上一镜结束状态：承接拆分镜头 2：突然，风铃声响起。她身体几不可查地一僵。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S5｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：中景，固定机位，时长约 3 秒。
起始：承接拆分镜头 2：突然，风铃声响起。她身体几不可查地一僵
过程：突然，风铃声响起。她身体几不可查地一僵
落点：林小夏身体微微绷直，脸上重新堆起标准但疲倦的欢迎表情，目光锁定在即将进入画面的门口方向。
光影：惨白荧光灯，从头顶直射，制造生硬阴影。货架商品标签反光刺眼。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 5] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵. Observable action timeline: 0.00-0.80s: 承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵 Camera: 固定机位. 0.80-3.00s: 突然，风铃声响起。她身体几不可查地一僵 Camera: 固定机位. 3.00-4.00s: 林小夏身体微微绷直，脸上重新堆起标准但疲倦的欢迎表情，目光锁定在即将进入画面的门口方向。 Camera: 固定机位. Final frame: 林小夏身体微微绷直，脸上重新堆起标准但疲倦的欢迎表情，目光锁定在即将进入画面的门口方向. Shot size: 中景; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 5｜便利店收银台｜3 秒｜16:9
首帧：承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵
镜头：中景，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：承接拆分镜头 2，突然，风铃声响起。她身体几不可查地一僵
- 1.05-2.40s：突然，风铃声响起。她身体几不可查地一僵
- 2.40-3.00s：林小夏身体微微绷直，脸上重新堆起标准但疲倦的欢迎表情，目光锁定在即将进入画面的门口方向。
结束落点：林小夏身体微微绷直，脸上重新堆起标准但疲倦的欢迎表情，目光锁定在即将进入画面的门口方向。
连续性约束：开头承接上一镜结束状态：承接拆分镜头 2：突然，风铃声响起。她身体几不可查地一僵。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S6｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：中景，缓慢滑轨移动，时长约 2 秒。
起始：门被推开，风铃作响。一个穿着深色连帽衫的男人（帽子拉低）进入画面，身影从黑暗过渡到灯光边缘。
过程：镜头跟随男人从门口向收银台方向缓慢推进。男人步伐沉稳，不快，但径直走向收银台，无视周围货架。
落点：男人停在收银台前，与林小夏形成对峙站位。其面部依然隐藏在帽檐阴影下。
光影：门口外部黑暗，男人进入时，荧光灯光从其背后勾勒轮廓，面部处于阴影中。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 6] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 门被推开，风铃作响。一个穿着深色连帽衫的男人（帽子拉低）进入画面，身影从黑暗过渡到灯光边缘. Observable action timeline: 0.00-0.80s: 门被推开，风铃作响。一个穿着深色连帽衫的男人（帽子拉低）进入画面，身影从黑暗过渡到灯光边缘。 Camera: 缓慢滑轨移动. 0.80-3.00s: 镜头跟随男人从门口向收银台方向缓慢推进。男人步伐沉稳，不快，但径直走向收银台，无视周围货架。 Camera: 缓慢滑轨移动. 3.00-4.00s: 男人停在收银台前，与林小夏形成对峙站位。其面部依然隐藏在帽檐阴影下。 Camera: 缓慢滑轨移动. Final frame: 男人停在收银台前，与林小夏形成对峙站位。其面部依然隐藏在帽檐阴影下. Shot size: 中景; camera movement: 缓慢滑轨移动. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 6｜便利店收银台｜2 秒｜16:9
首帧：门被推开，风铃作响。一个穿着深色连帽衫的男人（帽子拉低）进入画面，身影从黑暗过渡到灯光边缘。
镜头：中景，缓慢滑轨移动，转场 cut
动作时间线：
- 0.00-0.70s：门被推开，风铃作响。一个穿着深色连帽衫的男人（帽子拉低）进入画面，身影从黑暗过渡到灯光边缘。
- 0.70-1.60s：镜头跟随男人从门口向收银台方向缓慢推进。男人步伐沉稳，不快，但径直走向收银台，无视周围货架。
- 1.60-2.00s：男人停在收银台前，与林小夏形成对峙站位。其面部依然隐藏在帽檐阴影下。
结束落点：男人停在收银台前，与林小夏形成对峙站位。其面部依然隐藏在帽檐阴影下。
连续性约束：开头承接上一镜结束状态：林小夏身体微微绷直，脸上重新堆起标准但疲倦的欢迎表情，目光锁定在即将进入画面的门口方向。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S7｜便利店收银台

- 绑定资产数：3；参考图数：3
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：特写，固定机位，时长约 4 秒。
起始：便利店收银台上，林小夏刚将烟盒放下；神秘男人站在台前，手里攥着一张对折的旧照片。
过程：林小夏将烟盒平稳放在收银台上；神秘男人持着对折旧照片的手进入画面，并停在台面边缘。
落点：烟盒留在台面上，男人手中的对折旧照片停在前景，林小夏抬眼看向他。
对白/声音线索：买包烟。黄鹤楼。
还有这个。看看它。就像你看监控屏幕一样，仔细看看。
光影：台面上方灯光聚焦，突出烟盒与照片。男人手部和林小夏的手部在光区，其余较暗。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 7] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Reference image 3 (神秘男人): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 便利店收银台上，林小夏刚将烟盒放下。神秘男人站在台前，手里攥着一张对折的旧照片. Observable action timeline: 0.00-0.80s: 便利店收银台上，林小夏刚将烟盒放下。神秘男人站在台前，手里攥着一张对折的旧照片。 Camera: 固定机位. 0.80-3.00s: 林小夏将烟盒平稳放在收银台上。神秘男人持着对折旧照片的手进入画面，并停在台面边缘。 Camera: 固定机位. 3.00-4.00s: 烟盒留在台面上，男人手中的对折旧照片停在前景，林小夏抬眼看向他。 Camera: 固定机位. Final frame: 烟盒留在台面上，男人手中的对折旧照片停在前景，林小夏抬眼看向他. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 7｜便利店收银台｜4 秒｜16:9
首帧：便利店收银台上，林小夏刚将烟盒放下。神秘男人站在台前，手里攥着一张对折的旧照片。
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：便利店收银台上，林小夏刚将烟盒放下。神秘男人站在台前，手里攥着一张对折的旧照片。
- 0.80-3.00s：林小夏将烟盒平稳放在收银台上。神秘男人持着对折旧照片的手进入画面，并停在台面边缘。
- 3.00-4.00s：烟盒留在台面上，男人手中的对折旧照片停在前景，林小夏抬眼看向他。
对白/同期声线索：买包烟。黄鹤楼。还有这个。看看它。就像你看监控屏幕一样，仔细看看。
结束落点：烟盒留在台面上，男人手中的对折旧照片停在前景，林小夏抬眼看向他。
连续性约束：开头承接上一镜结束状态：男人停在收银台前，与林小夏形成对峙站位。其面部依然隐藏在帽檐阴影下。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S8｜便利店收银台

- 绑定资产数：3；参考图数：3
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：特写，固定机位，时长约 4 秒。
起始：烟盒留在收银台上，神秘男人手中的对折旧照片停在前景，林小夏抬眼看向他。
过程：神秘男人将对折旧照片放到烟盒旁并缓慢推向林小夏；林小夏的视线从烟盒移到照片上，表情由敷衍转为警觉。
落点：旧照片停在台面中央，男人的手收回画外，林小夏的目光凝固在照片上。
光影：台面上方灯光聚焦，突出烟盒与照片。男人手部和林小夏的手部在光区，其余较暗。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 8] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Reference image 3 (神秘男人): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 烟盒留在收银台上，神秘男人手中的对折旧照片停在前景，林小夏抬眼看向他. Observable action timeline: 0.00-0.80s: 烟盒留在收银台上，神秘男人手中的对折旧照片停在前景，林小夏抬眼看向他。 Camera: 固定机位. 0.80-3.00s: 神秘男人将对折旧照片放到烟盒旁并缓慢推向林小夏。林小夏的视线从烟盒移到照片上，表情由敷衍转为警觉。 Camera: 固定机位. 3.00-4.00s: 旧照片停在台面中央，男人的手收回画外，林小夏的目光凝固在照片上。 Camera: 固定机位. Final frame: 旧照片停在台面中央，男人的手收回画外，林小夏的目光凝固在照片上. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 8｜便利店收银台｜4 秒｜16:9
首帧：烟盒留在收银台上，神秘男人手中的对折旧照片停在前景，林小夏抬眼看向他。
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：烟盒留在收银台上，神秘男人手中的对折旧照片停在前景，林小夏抬眼看向他。
- 0.80-3.00s：神秘男人将对折旧照片放到烟盒旁并缓慢推向林小夏。林小夏的视线从烟盒移到照片上，表情由敷衍转为警觉。
- 3.00-4.00s：旧照片停在台面中央，男人的手收回画外，林小夏的目光凝固在照片上。
结束落点：旧照片停在台面中央，男人的手收回画外，林小夏的目光凝固在照片上。
连续性约束：开头承接上一镜结束状态：烟盒留在台面上，男人手中的对折旧照片停在前景，林小夏抬眼看向他。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S9｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：极特写，缓慢推进，时长约 4 秒。
起始：林小夏的指尖触碰到照片边缘。她眼神从警惕转为专注。
过程：随后镜头极缓慢推向林小夏展开照片的动作和她的脸部
落点：承接拆分镜头 6：男人的手缩回
对白/声音线索：……这是谁？
我也想知道。也许，你比我更清楚。
光影：顶光直射照片表面和林小夏的眼睛，照片折痕和灰尘清晰可见，瞳孔反射灯光。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 9] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏的指尖触碰到照片边缘。她眼神从警惕转为专注. Observable action timeline: 0.00-0.80s: 林小夏的指尖触碰到照片边缘。她眼神从警惕转为专注。 Camera: 缓慢推进. 0.80-3.00s: 随后镜头极缓慢推向林小夏展开照片的动作和她的脸部 Camera: 缓慢推进. 3.00-4.00s: 承接拆分镜头 6，男人的手缩回 Camera: 缓慢推进. Final frame: 承接拆分镜头 6，男人的手缩回. Shot size: 极特写; camera movement: 缓慢推进. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 9｜便利店收银台｜4 秒｜16:9
首帧：林小夏的指尖触碰到照片边缘。她眼神从警惕转为专注。
镜头：极特写，缓慢推进，转场 cut
动作时间线：
- 0.00-0.80s：林小夏的指尖触碰到照片边缘。她眼神从警惕转为专注。
- 0.80-3.00s：随后镜头极缓慢推向林小夏展开照片的动作和她的脸部
- 3.00-4.00s：承接拆分镜头 6，男人的手缩回
对白/同期声线索：……这是谁？ 我也想知道。也许，你比我更清楚。
结束落点：承接拆分镜头 6，男人的手缩回
连续性约束：开头承接上一镜结束状态：旧照片停在台面中央，男人的手收回画外，林小夏的目光凝固在照片上。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S10｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：极特写，固定机位，时长约 4 秒。
起始：承接拆分镜头 6：男人的手缩回
过程：男人的手缩回
落点：镜头停留在林小夏的眼睛特写上，她眼神中充满震惊和难以置信，目光死死盯着照片（画外）。男人低沉的回应声从画外传来。
光影：顶光直射照片表面和林小夏的眼睛，照片折痕和灰尘清晰可见，瞳孔反射灯光。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 10] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 6，男人的手缩回. Observable action timeline: 0.00-0.80s: 承接拆分镜头 6，男人的手缩回 Camera: 固定机位. 0.80-3.00s: 男人的手缩回 Camera: 固定机位. 3.00-4.00s: 镜头停留在林小夏的眼睛特写上，她眼神中充满震惊和难以置信，目光死死盯着照片（画外）。男人低沉的回应声从画外传来。 Camera: 固定机位. Final frame: 镜头停留在林小夏的眼睛特写上，她眼神中充满震惊和难以置信，目光死死盯着照片（画外）。男人低沉的回应声从画外传来. Shot size: 极特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 10｜便利店收银台｜4 秒｜16:9
首帧：承接拆分镜头 6，男人的手缩回
镜头：极特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：承接拆分镜头 6，男人的手缩回
- 0.80-3.00s：男人的手缩回
- 3.00-4.00s：镜头停留在林小夏的眼睛特写上，她眼神中充满震惊和难以置信，目光死死盯着照片（画外）。男人低沉的回应声从画外传来。
结束落点：镜头停留在林小夏的眼睛特写上，她眼神中充满震惊和难以置信，目光死死盯着照片（画外）。男人低沉的回应声从画外传来。
连续性约束：开头承接上一镜结束状态：承接拆分镜头 6：男人的手缩回。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S11｜便利店收银台

- 绑定资产数：3；参考图数：3
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：中景，固定机位，时长约 5 秒。
起始：林小夏放下照片，指尖在上面留下压痕，语气带着被冒犯的冷淡。她试图将照片推回。
过程：神秘男人没有接照片，他的手再次拿起烟，但目光落在冰美式上，进行私人提问。林小夏身体前倾，彻底警觉，脚尖转向门口。男人最终拿起照片，仔细重新对折，放回原位，转身走向门口，在离开前说出关键台词。
落点：神秘男人身影消失在门口，风铃再次响起。林小夏独自站在收银台前，脸色苍白，看着被放回原位的照片。
对白/声音线索：先生，恶作剧？这张照片和我无关。
照片不会说谎。但眼睛会。尤其是，当一个人习惯了透过屏幕看世界的时候。晚安，林小夏。
光影：保持顶光，但男人面部阴影加深，显得轮廓更冷硬。林小夏侧脸紧绷。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 11] Live-action cinematic footage. Scene: 便利店收银台. Duration: 5 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Reference image 3 (神秘男人): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏放下照片，指尖在上面留下压痕，语气带着被冒犯的冷淡。她试图将照片推回. Observable action timeline: 0.00-1.00s: 林小夏放下照片，指尖在上面留下压痕，语气带着被冒犯的冷淡。她试图将照片推回。 Camera: 固定机位. 1.00-3.75s: 神秘男人没有接照片，他的手再次拿起烟，但目光落在冰美式上，进行私人提问。林小夏身体前倾，彻底警觉，脚尖转向门口。男人最终拿起照片，仔细重新对折，放回原位，转身走向门口，在离开前说出关键口型动作。 Camera: 固定机位. 3.75-5.00s: 神秘男人身影消失在门口，风铃再次响起。林小夏独自站在收银台前，脸色苍白，看着被放回原位的照片。 Camera: 固定机位. Final frame: 神秘男人身影消失在门口，风铃再次响起。林小夏独自站在收银台前，脸色苍白，看着被放回原位的照片. Shot size: 中景; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 11｜便利店收银台｜5 秒｜16:9
首帧：林小夏放下照片，指尖在上面留下压痕，语气带着被冒犯的冷淡。她试图将照片推回。
镜头：中景，固定机位，转场 cut
动作时间线：
- 0.00-1.00s：林小夏放下照片，指尖在上面留下压痕，语气带着被冒犯的冷淡。她试图将照片推回。
- 1.00-3.75s：神秘男人没有接照片，他的手再次拿起烟，但目光落在冰美式上，进行私人提问。林小夏身体前倾，彻底警觉，脚尖转向门口。男人最终拿起照片，仔细重新对折，放回原位，转身走向门口，在离开前说出关键口型动作。
- 3.75-5.00s：神秘男人身影消失在门口，风铃再次响起。林小夏独自站在收银台前，脸色苍白，看着被放回原位的照片。
对白/同期声线索：先生，恶作剧？这张照片和我无关。照片不会说谎。但眼睛会。尤其是，当一个人习惯了透过屏幕看世界的时候。晚安，林小夏。
结束落点：神秘男人身影消失在门口，风铃再次响起。林小夏独自站在收银台前，脸色苍白，看着被放回原位的照片。
连续性约束：开头承接上一镜结束状态：镜头停留在林小夏的眼睛特写上，她眼神中充满震惊和难以置信，目光死死盯着照片（画外）。男人低沉的回应声从画外传来。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S12｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：特写，固定机位，时长约 4 秒。
起始：林小夏确认男人离开，迅速拉下半卷帘门。她回到收银台前，目光锁定照片，脸上慵懒尽褪，只有冰冷的凝重。
过程：她没有犹豫，再次伸手展开照片
落点：承接拆分镜头 10：镜头切换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上
对白/声音线索：……怎么会。
光影：荧光灯光刺眼，聚焦在再次展开的照片和林小夏的领口。光线冰冷，缺乏温度。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 12] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏确认男人离开，迅速拉下半卷帘门。她回到收银台前，目光锁定照片，脸上慵懒尽褪，只有冰冷的凝重. Observable action timeline: 0.00-0.80s: 林小夏确认男人离开，迅速拉下半卷帘门。她回到收银台前，目光锁定照片，脸上慵懒尽褪，只有冰冷的凝重。 Camera: 固定机位. 0.80-3.00s: 她没有犹豫，再次伸手展开照片 Camera: 固定机位. 3.00-4.00s: 承接拆分镜头 10，镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上 Camera: 固定机位. Final frame: 承接拆分镜头 10，镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 12｜便利店收银台｜4 秒｜16:9
首帧：林小夏确认男人离开，迅速拉下半卷帘门。她回到收银台前，目光锁定照片，脸上慵懒尽褪，只有冰冷的凝重。
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：林小夏确认男人离开，迅速拉下半卷帘门。她回到收银台前，目光锁定照片，脸上慵懒尽褪，只有冰冷的凝重。
- 0.80-3.00s：她没有犹豫，再次伸手展开照片
- 3.00-4.00s：承接拆分镜头 10，镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上
对白/同期声线索：……怎么会。
结束落点：承接拆分镜头 10，镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上
连续性约束：开头承接上一镜结束状态：神秘男人身影消失在门口，风铃再次响起。林小夏独自站在收银台前，脸色苍白，看着被放回原位的照片。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S13｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：特写，固定机位，时长约 4 秒。
起始：承接拆分镜头 10：镜头切换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上
过程：镜头切换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上
落点：承接拆分镜头 11：镜头切回林小夏的脸，她瞳孔收缩，倒吸冷气
光影：荧光灯光刺眼，聚焦在再次展开的照片和林小夏的领口。光线冰冷，缺乏温度。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 13] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 10，镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上. Observable action timeline: 0.00-0.80s: 承接拆分镜头 10，镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上 Camera: 固定机位. 0.80-3.00s: 镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上 Camera: 固定机位. 3.00-4.00s: 承接拆分镜头 11，镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气 Camera: 固定机位. Final frame: 承接拆分镜头 11，镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 13｜便利店收银台｜4 秒｜16:9
首帧：承接拆分镜头 10，镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：承接拆分镜头 10，镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上
- 0.80-3.00s：镜头转为换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上
- 3.00-4.00s：承接拆分镜头 11，镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气
结束落点：承接拆分镜头 11，镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气
连续性约束：开头承接上一镜结束状态：承接拆分镜头 10：镜头切换为照片特写，焦点落在照片中女人连衣裙领口的银色飞鸟胸针上。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S14｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：特写，固定机位，时长约 4 秒。
起始：承接拆分镜头 11：镜头切回林小夏的脸，她瞳孔收缩，倒吸冷气
过程：镜头切回林小夏的脸，她瞳孔收缩，倒吸冷气
落点：承接拆分镜头 8：她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店
光影：荧光灯光刺眼，聚焦在再次展开的照片和林小夏的领口。光线冰冷，缺乏温度。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 14] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 11，镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气. Observable action timeline: 0.00-0.80s: 承接拆分镜头 11，镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气 Camera: 固定机位. 0.80-3.00s: 镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气 Camera: 固定机位. 3.00-4.00s: 承接拆分镜头 8，她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店 Camera: 固定机位. Final frame: 承接拆分镜头 8，她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 14｜便利店收银台｜4 秒｜16:9
首帧：承接拆分镜头 11，镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：承接拆分镜头 11，镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气
- 0.80-3.00s：镜头转为回林小夏的脸，她瞳孔收缩，倒吸冷气
- 3.00-4.00s：承接拆分镜头 8，她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店
结束落点：承接拆分镜头 8，她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店
连续性约束：开头承接上一镜结束状态：承接拆分镜头 11：镜头切回林小夏的脸，她瞳孔收缩，倒吸冷气。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S15｜便利店收银台

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：便利店收银台
镜头：特写，固定机位，时长约 4 秒。
起始：承接拆分镜头 8：她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店
过程：她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店
落点：林小夏的手指触碰到自己胸前的胸针，脸色苍白，眼神从震惊变为深邃的迷茫和恐惧。她抬起头，环顾四周，便利店仿佛变得无比陌生。画面定格在她与监控屏幕中“自己”的对峙感。
光影：荧光灯光刺眼，聚焦在再次展开的照片和林小夏的领口。光线冰冷，缺乏温度。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 15] Live-action cinematic footage. Scene: 便利店收银台. Duration: 4 seconds. Reference assignments: Reference image 1 (便利店收银台): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 8，她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店. Observable action timeline: 0.00-0.80s: 承接拆分镜头 8，她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店 Camera: 固定机位. 0.80-3.00s: 她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店 Camera: 固定机位. 3.00-4.00s: 林小夏的手指触碰到自己胸前的胸针，脸色苍白，眼神从震惊变为深邃的迷茫和恐惧。她抬起头，环顾四周，便利店仿佛变得无比陌生。画面定格在她与监控屏幕中“自己”的对峙感。 Camera: 固定机位. Final frame: 林小夏的手指触碰到自己胸前的胸针，脸色苍白，眼神从震惊变为深邃的迷茫和恐惧。她抬起头，环顾四周，便利店仿佛变得无比陌生。画面定格在她与监控屏幕中“自己”的对峙感. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 15｜便利店收银台｜4 秒｜16:9
首帧：承接拆分镜头 8，她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：承接拆分镜头 8，她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店
- 0.80-3.00s：她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店
- 3.00-4.00s：林小夏的手指触碰到自己胸前的胸针，脸色苍白，眼神从震惊变为深邃的迷茫和恐惧。她抬起头，环顾四周，便利店仿佛变得无比陌生。画面定格在她与监控屏幕中“自己”的对峙感。
结束落点：林小夏的手指触碰到自己胸前的胸针，脸色苍白，眼神从震惊变为深邃的迷茫和恐惧。她抬起头，环顾四周，便利店仿佛变得无比陌生。画面定格在她与监控屏幕中“自己”的对峙感。
连续性约束：开头承接上一镜结束状态：承接拆分镜头 8：她的手下意识摸向自己制服领口内侧——那里别着一模一样的胸针。她低声自语，眼神扫视陌生的便利店。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：便利店收银台。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S16｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：中景，固定机位，时长约 3 秒。
起始：林小夏叼着冰美式，疲惫地坐进转椅，身体后仰，双脚离地。
过程：她咬开塑料膜，吸管戳入（“啵”声），发出不满嘟囔。无意识踢到主机，噪音变化。
落点：她身体稍稳，目光第一次懒散地扫向监控屏幕。
对白/声音线索：…烦死了。还有两小时才交班…
光影：昏暗，仅屏幕蓝光与主机指示灯微弱闪烁，主要光源来自监控屏幕，照亮人物上半身。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 16] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏叼着冰美式，疲惫地坐进转椅，身体后仰，双脚离地. Observable action timeline: 0.00-0.80s: 林小夏叼着冰美式，疲惫地坐进转椅，身体后仰，双脚离地。 Camera: 固定机位. 0.80-3.00s: 她咬开塑料膜，吸管戳入（“啵”声），发出不满嘟囔。无意识踢到主机，噪音变化。 Camera: 固定机位. 3.00-4.00s: 她身体稍稳，目光第一次懒散地扫向监控屏幕。 Camera: 固定机位. Final frame: 她身体稍稳，目光第一次懒散地扫向监控屏幕. Shot size: 中景; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 16｜监控室｜3 秒｜16:9
首帧：林小夏叼着冰美式，疲惫地坐进转椅，身体后仰，双脚离地。
镜头：中景，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：林小夏叼着冰美式，疲惫地坐进转椅，身体后仰，双脚离地。
- 1.05-2.40s：她咬开塑料膜，吸管戳入（“啵”声），发出不满嘟囔。无意识踢到主机，噪音变化。
- 2.40-3.00s：她身体稍稳，目光第一次懒散地扫向监控屏幕。
对白/同期声线索：…烦死了。还有两小时才交班…
结束落点：她身体稍稳，目光第一次懒散地扫向监控屏幕。
连续性约束：开头承接上一镜结束状态：林小夏的手指触碰到自己胸前的胸针，脸色苍白，眼神从震惊变为深邃的迷茫和恐惧。她抬起头，环顾四周，便利店仿佛变得无比陌生。画面定格在她与监控屏幕中“自己”的对峙感。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S17｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：特写，缓慢推进，时长约 4 秒。
起始：林小夏打着哈欠，眼角有泪光，目光随意地扫过监控画面。
过程：随后镜头缓缓推向她的脸
落点：承接拆分镜头 10：保留结尾的信息揭示或情绪反应
对白/声音线索：（无台词）
光影：主光为监控屏幕冷光，映照在林小夏面部，突显她瞳孔的变化。阴影加重。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 17] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏打着哈欠，眼角有泪光，目光随意地扫过监控画面. Observable action timeline: 0.00-0.80s: 林小夏打着哈欠，眼角有泪光，目光随意地扫过监控画面。 Camera: 缓慢推进. 0.80-3.00s: 随后镜头缓缓推向她的脸 Camera: 缓慢推进. 3.00-4.00s: 承接拆分镜头 10，保留结尾的信息揭示或情绪反应 Camera: 缓慢推进. Final frame: 承接拆分镜头 10，保留结尾的信息揭示或情绪反应. Shot size: 特写; camera movement: 缓慢推进. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 17｜监控室｜4 秒｜16:9
首帧：林小夏打着哈欠，眼角有泪光，目光随意地扫过监控画面。
镜头：特写，缓慢推进，转场 cut
动作时间线：
- 0.00-0.80s：林小夏打着哈欠，眼角有泪光，目光随意地扫过监控画面。
- 0.80-3.00s：随后镜头缓缓推向她的脸
- 3.00-4.00s：承接拆分镜头 10，保留结尾的信息揭示或情绪反应
对白/同期声线索：（无口型动作）
结束落点：承接拆分镜头 10，保留结尾的信息揭示或情绪反应
连续性约束：开头承接上一镜结束状态：她身体稍稳，目光第一次懒散地扫向监控屏幕。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S18｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：特写，固定机位，时长约 4 秒。
起始：承接拆分镜头 10：保留结尾的信息揭示或情绪反应
过程：保留结尾的信息揭示或情绪反应
落点：林小夏身体前倾，紧盯屏幕，表情从慵懒转为惊疑不定，下颌线紧绷。
光影：主光为监控屏幕冷光，映照在林小夏面部，突显她瞳孔的变化。阴影加重。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 18] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 10，保留结尾的信息揭示或情绪反应. Observable action timeline: 0.00-0.80s: 承接拆分镜头 10，保留结尾的信息揭示或情绪反应 Camera: 固定机位. 0.80-3.00s: 保留结尾的信息揭示或情绪反应 Camera: 固定机位. 3.00-4.00s: 林小夏身体前倾，紧盯屏幕，表情从慵懒转为惊疑不定，下颌线紧绷。 Camera: 固定机位. Final frame: 林小夏身体前倾，紧盯屏幕，表情从慵懒转为惊疑不定，下颌线紧绷. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 18｜监控室｜4 秒｜16:9
首帧：承接拆分镜头 10，保留结尾的信息揭示或情绪反应
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：承接拆分镜头 10，保留结尾的信息揭示或情绪反应
- 0.80-3.00s：保留结尾的信息揭示或情绪反应
- 3.00-4.00s：林小夏身体前倾，紧盯屏幕，表情从慵懒转为惊疑不定，下颌线紧绷。
结束落点：林小夏身体前倾，紧盯屏幕，表情从慵懒转为惊疑不定，下颌线紧绷。
连续性约束：开头承接上一镜结束状态：承接拆分镜头 10：保留结尾的信息揭示或情绪反应。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S19｜监控室

- 绑定资产数：1；参考图数：1
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：极特写，固定机位，时长约 3 秒。
起始：监控画面显示收银台俯角，台面有冰美式水渍轮廓。
过程：镜头对准监控屏幕画面。画面静止，但在屏幕反光与像素噪点中，一张对折的旧照片轮廓隐约可见，旁边是杯子印记。
落点：照片轮廓在屏幕上清晰可辨，引发疑问。
对白/声音线索：（无台词）
光影：屏幕像素点光斑，强烈反差，突出照片轮廓。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 19] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Do not swap the roles of reference images. Opening state: 监控画面显示收银台俯角，台面有冰美式水渍轮廓. Observable action timeline: 0.00-0.80s: 监控画面显示收银台俯角，台面有冰美式水渍轮廓。 Camera: 固定机位. 0.80-3.00s: 镜头对准监控屏幕画面。画面静止，但在屏幕反光与像素噪点中，一张对折的旧照片轮廓隐约可见，旁边是杯子印记。 Camera: 固定机位. 3.00-4.00s: 照片轮廓在屏幕上清晰可辨，引发疑问。 Camera: 固定机位. Final frame: 照片轮廓在屏幕上清晰可辨，引发疑问. Shot size: 极特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 19｜监控室｜3 秒｜16:9
首帧：监控画面显示收银台俯角，台面有冰美式水渍轮廓。
镜头：极特写，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：监控画面显示收银台俯角，台面有冰美式水渍轮廓。
- 1.05-2.40s：镜头对准监控屏幕画面。画面静止，但在屏幕反光与像素噪点中，一张对折的旧照片轮廓隐约可见，旁边是杯子印记。
- 2.40-3.00s：照片轮廓在屏幕上清晰可辨，引发疑问。
对白/同期声线索：（无口型动作）
结束落点：照片轮廓在屏幕上清晰可辨，引发疑问。
连续性约束：开头承接上一镜结束状态：林小夏身体前倾，紧盯屏幕，表情从慵懒转为惊疑不定，下颌线紧绷。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S20｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：中景，固定机位，时长约 3 秒。
起始：林小夏身体前倾，手撑在桌边，眼睛紧盯着某块屏幕。
过程：她猛地坐直（椅子刺耳摩擦），低语“那照片”，双手快速撑桌。眼神锐利，快速扫视所有屏幕，确认其他屏幕无异常。
落点：她确定异常只存在于那块屏幕，表情彻底转为冰冷、专注的探究。
对白/声音线索：…那照片…
光影：屏幕冷光成为唯一光源，照亮林小夏上半身和杂乱桌面，人物背后陷入黑暗。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 20] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏身体前倾，手撑在桌边，眼睛紧盯着某块屏幕. Observable action timeline: 0.00-0.80s: 林小夏身体前倾，手撑在桌边，眼睛紧盯着某块屏幕。 Camera: 固定机位. 0.80-3.00s: 她猛地坐直（椅子刺耳摩擦），低语“那照片”，双手快速撑桌。眼神锐利，快速扫视所有屏幕，确认其他屏幕无异常。 Camera: 固定机位. 3.00-4.00s: 她确定异常只存在于那块屏幕，表情彻底转为冰冷、专注的探究。 Camera: 固定机位. Final frame: 她确定异常只存在于那块屏幕，表情彻底转为冰冷、专注的探究. Shot size: 中景; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 20｜监控室｜3 秒｜16:9
首帧：林小夏身体前倾，手撑在桌边，眼睛紧盯着某块屏幕。
镜头：中景，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：林小夏身体前倾，手撑在桌边，眼睛紧盯着某块屏幕。
- 1.05-2.40s：她猛地坐直（椅子刺耳摩擦），低语“那照片”，双手快速撑桌。眼神锐利，快速扫视所有屏幕，确认其他屏幕无异常。
- 2.40-3.00s：她确定异常只存在于那块屏幕，表情彻底转为冰冷、专注的探究。
对白/同期声线索：…那照片…
结束落点：她确定异常只存在于那块屏幕，表情彻底转为冰冷、专注的探究。
连续性约束：开头承接上一镜结束状态：照片轮廓在屏幕上清晰可辨，引发疑问。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S21｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：特写，固定机位，时长约 3 秒。
起始：林小夏右手抓向鼠标。
过程：她操作鼠标，光标在屏幕上移动，但画面是实时监控，无法回放。她抿紧嘴唇，低声咒骂。
落点：她松开鼠标，表情懊恼，开始快速扫视桌面寻找其他方法。
对白/声音线索：该死…实时的。
光影：同上，光线集中在她操作鼠标的手和面部下侧。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 21] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏右手抓向鼠标. Observable action timeline: 0.00-0.80s: 林小夏右手抓向鼠标。 Camera: 固定机位. 0.80-3.00s: 她操作鼠标，光标在屏幕上移动，但画面是实时监控，无法回放。她抿紧嘴唇，低声咒骂。 Camera: 固定机位. 3.00-4.00s: 她松开鼠标，表情懊恼，开始快速扫视桌面寻找其他方法。 Camera: 固定机位. Final frame: 她松开鼠标，表情懊恼，开始快速扫视桌面寻找其他方法. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 21｜监控室｜3 秒｜16:9
首帧：林小夏右手抓向鼠标。
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-1.05s：林小夏右手抓向鼠标。
- 1.05-2.40s：她操作鼠标，光标在屏幕上移动，但画面是实时监控，无法回放。她抿紧嘴唇，低声咒骂。
- 2.40-3.00s：她松开鼠标，表情懊恼，开始快速扫视桌面寻找其他方法。
对白/同期声线索：该死…实时的。
结束落点：她松开鼠标，表情懊恼，开始快速扫视桌面寻找其他方法。
连续性约束：开头承接上一镜结束状态：她确定异常只存在于那块屏幕，表情彻底转为冰冷、专注的探究。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S22｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：特写，缓慢pan，时长约 4 秒。
起始：林小夏双手快速拉开第一个抽屉翻找。
过程：镜头跟随她的手和视线。她有条理地翻找抽屉：先第一个（收银纸、过期糖），再第二个（电线、电池），动作迅捷，与之前形象反差巨大
落点：承接拆分镜头 14：她眼神冷静扫描
对白/声音线索：（无台词）
光影：光线随她翻找动作在杂乱抽屉和她专注的脸上移动。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 22] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏双手快速拉开第一个抽屉翻找. Observable action timeline: 0.00-0.80s: 林小夏双手快速拉开第一个抽屉翻找。 Camera: 缓慢pan. 0.80-3.00s: 镜头跟随她的手和视线。她有条理地翻找抽屉，先第一个（收银纸、过期糖），再第二个（电线、电池），动作迅捷，与之前形象反差巨大 Camera: 缓慢pan. 3.00-4.00s: 承接拆分镜头 14，她眼神冷静扫描 Camera: 缓慢pan. Final frame: 承接拆分镜头 14，她眼神冷静扫描. Shot size: 特写; camera movement: 缓慢pan. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 22｜监控室｜4 秒｜16:9
首帧：林小夏双手快速拉开第一个抽屉翻找。
镜头：特写，缓慢pan，转场 cut
动作时间线：
- 0.00-0.80s：林小夏双手快速拉开第一个抽屉翻找。
- 0.80-3.00s：镜头跟随她的手和视线。她有条理地翻找抽屉，先第一个（收银纸、过期糖），再第二个（电线、电池），动作迅捷，与之前形象反差巨大
- 3.00-4.00s：承接拆分镜头 14，她眼神冷静扫描
对白/同期声线索：（无口型动作）
结束落点：承接拆分镜头 14，她眼神冷静扫描
连续性约束：开头承接上一镜结束状态：她松开鼠标，表情懊恼，开始快速扫视桌面寻找其他方法。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S23｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：特写，固定机位，时长约 4 秒。
起始：承接拆分镜头 14：她眼神冷静扫描
过程：她眼神冷静扫描
落点：她拉开最底层抽屉，手在角落摸到什么，眼神微动（发现复位键），但继续翻找，摸出“驱动备份”光盘盒。
光影：光线随她翻找动作在杂乱抽屉和她专注的脸上移动。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 23] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 14，她眼神冷静扫描. Observable action timeline: 0.00-0.80s: 承接拆分镜头 14，她眼神冷静扫描 Camera: 固定机位. 0.80-3.00s: 她眼神冷静扫描 Camera: 固定机位. 3.00-4.00s: 她拉开最底层抽屉，手在角落摸到什么，眼神微动（发现复位键），但继续翻找，摸出“驱动备份”光盘盒。 Camera: 固定机位. Final frame: 她拉开最底层抽屉，手在角落摸到什么，眼神微动（发现复位键），但继续翻找，摸出“驱动备份”光盘盒. Shot size: 特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 23｜监控室｜4 秒｜16:9
首帧：承接拆分镜头 14，她眼神冷静扫描
镜头：特写，固定机位，转场 cut
动作时间线：
- 0.00-0.80s：承接拆分镜头 14，她眼神冷静扫描
- 0.80-3.00s：她眼神冷静扫描
- 3.00-4.00s：她拉开最底层抽屉，手在角落摸到什么，眼神微动（发现复位键），但继续翻找，摸出“驱动备份”光盘盒。
结束落点：她拉开最底层抽屉，手在角落摸到什么，眼神微动（发现复位键），但继续翻找，摸出“驱动备份”光盘盒。
连续性约束：开头承接上一镜结束状态：承接拆分镜头 14：她眼神冷静扫描。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S24｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：中景，缓慢推进，时长约 5 秒。
起始：林小夏将光盘塞入光驱，操作老旧的监控软件。她叼着冰美式喝了一大口（放松掩饰），然后表情恢复冰冷专注。
过程：镜头缓慢推向她的侧脸和电脑屏幕。她熟练操作，时间轴被拖动、快进。屏幕画面飞速播放。她在【3:15】左右停止拖动，按下播放。
落点：她的脸被屏幕光照亮，表情极其专注，盯着开始正常速度回放的监控画面——画面中，“她”正在打瞌睡，台面空无一物。
对白/声音线索：（无台词）
光影：电脑屏幕成为主光源，照亮林小夏专注的脸和键盘区域。环境更暗。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 24] Live-action cinematic footage. Scene: 监控室. Duration: 5 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 林小夏将光盘塞入光驱，操作老旧的监控软件。她叼着冰美式喝了一大口（放松掩饰），然后表情恢复冰冷专注. Observable action timeline: 0.00-1.00s: 林小夏将光盘塞入光驱，操作老旧的监控软件。她叼着冰美式喝了一大口（放松掩饰），然后表情恢复冰冷专注。 Camera: 缓慢推进. 1.00-3.75s: 镜头缓慢推向她的侧脸和电脑屏幕。她熟练操作，时间轴被拖动、快进。屏幕画面飞速播放。她在3，15左右停止拖动，按下播放。 Camera: 缓慢推进. 3.75-5.00s: 她的脸被屏幕光照亮，表情极其专注，盯着开始正常速度回放的监控画面——画面中，“她”正在打瞌睡，台面空无一物。 Camera: 缓慢推进. Final frame: 她的脸被屏幕光照亮，表情极其专注，盯着开始正常速度回放的监控画面——画面中，“她”正在打瞌睡，台面空无一物. Shot size: 中景; camera movement: 缓慢推进. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 24｜监控室｜5 秒｜16:9
首帧：林小夏将光盘塞入光驱，操作老旧的监控软件。她叼着冰美式喝了一大口（放松掩饰），然后表情恢复冰冷专注。
镜头：中景，缓慢推进，转场 cut
动作时间线：
- 0.00-1.00s：林小夏将光盘塞入光驱，操作老旧的监控软件。她叼着冰美式喝了一大口（放松掩饰），然后表情恢复冰冷专注。
- 1.00-3.75s：镜头缓慢推向她的侧脸和电脑屏幕。她熟练操作，时间轴被拖动、快进。屏幕画面飞速播放。她在3，15左右停止拖动，按下播放。
- 3.75-5.00s：她的脸被屏幕光照亮，表情极其专注，盯着开始正常速度回放的监控画面——画面中，“她”正在打瞌睡，台面空无一物。
对白/同期声线索：（无口型动作）
结束落点：她的脸被屏幕光照亮，表情极其专注，盯着开始正常速度回放的监控画面——画面中，“她”正在打瞌睡，台面空无一物。
连续性约束：开头承接上一镜结束状态：她拉开最底层抽屉，手在角落摸到什么，眼神微动（发现复位键），但继续翻找，摸出“驱动备份”光盘盒。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S25｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：极特写，固定机位，时长约 4 秒。
起始：监控回放画面：时间【3:15】左右，收银台空荡，“林小夏”在打瞌睡。
过程：随后一只戴着深色手套（或只见手）的手从画面右侧（监控盲区边缘）伸入。将一张对折的旧照片轻轻放在台面上
落点：承接拆分镜头 16：然后收回。镜头聚焦于那只手完成放置并确认的动作
对白/声音线索：（无台词）
光影：电脑屏幕光，清晰照亮回放画面细节。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 25] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 监控回放画面，时间3，15左右，收银台空荡，“林小夏”在打瞌睡. Observable action timeline: 0.00-0.80s: 监控回放画面，时间3，15左右，收银台空荡，“林小夏”在打瞌睡。 Camera: 固定机位. 0.80-3.00s: 随后一只戴着深色手套（或只见手）的手从画面右侧（监控盲区边缘）伸入。将一张对折的旧照片轻轻放在台面上 Camera: 固定机位. 3.00-4.00s: 承接拆分镜头 16，然后收回。镜头聚焦于那只手完成放置并确认的动作 Camera: 固定机位. Final frame: 承接拆分镜头 16，然后收回。镜头聚焦于那只手完成放置并确认的动作. Shot size: 极特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

overall_soundscape:
冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 25｜监控室｜4 秒｜16:9
首帧：监控回放画面，时间3，15左右，收银台空荡，“林小夏”在打瞌睡。
镜头：极特写，固定机位，转场 fade to black
动作时间线：
- 0.00-0.80s：监控回放画面，时间3，15左右，收银台空荡，“林小夏”在打瞌睡。
- 0.80-3.00s：随后一只戴着深色手套（或只见手）的手从画面右侧（监控盲区边缘）伸入。将一张对折的旧照片轻轻放在台面上
- 3.00-4.00s：承接拆分镜头 16，然后收回。镜头聚焦于那只手完成放置并确认的动作
对白/同期声线索：（无口型动作）
结束落点：承接拆分镜头 16，然后收回。镜头聚焦于那只手完成放置并确认的动作
连续性约束：开头承接上一镜结束状态：她的脸被屏幕光照亮，表情极其专注，盯着开始正常速度回放的监控画面——画面中，“她”正在打瞌睡，台面空无一物。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：冷白荧光灯低鸣、冰柜压缩机细响、门铃余音与深夜便利店的空旷室内底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```

### E1-S26｜监控室

- 绑定资产数：2；参考图数：2
- 导演分镜可编辑：True
- 机器提示词提交 API：False

导演分镜语言：

```text
场景：监控室
镜头：极特写，固定机位，时长约 4 秒。
起始：承接拆分镜头 16：然后收回。镜头聚焦于那只手完成放置并确认的动作
过程：然后收回。镜头聚焦于那只手完成放置并确认的动作
落点：手收回，照片静止在台面上。回放画面显示，“林小夏”即将抬起头。镜头聚焦于那只手完成放置并确认的动作。
光影：电脑屏幕光，清晰照亮回放画面细节。
```

MiniMax H3 / WebUI 导出：

```text
integrated_multimodal_description:
[Shot 26] Live-action cinematic footage. Scene: 监控室. Duration: 4 seconds. Reference assignments: Reference image 1 (监控室): use only for scene layout, spatial proportions, and lighting. Reference image 2 (林小夏): use only for character identity, face, hair, costume, and body silhouette. Do not swap the roles of reference images. Opening state: 承接拆分镜头 16，然后收回。镜头聚焦于那只手完成放置并确认的动作. Observable action timeline: 0.00-0.80s: 承接拆分镜头 16，然后收回。镜头聚焦于那只手完成放置并确认的动作 Camera: 固定机位. 0.80-3.00s: 然后收回。镜头聚焦于那只手完成放置并确认的动作 Camera: 固定机位. 3.00-4.00s: 手收回，照片静止在台面上。回放画面显示，“林小夏”即将抬起头。镜头聚焦于那只手完成放置并确认的动作。 Camera: 固定机位. Final frame: 手收回，照片静止在台面上。回放画面显示，“林小夏”即将抬起头。镜头聚焦于那只手完成放置并确认的动作. Shot size: 极特写; camera movement: 固定机位. Maintain continuity of face, costume, hair, prop state, lighting, and spatial layout. Hard constraints: 不要字幕、水印、logo、分屏、四宫格或界面文字。 不要改变人物身份、服装、发型、场景布局和关键道具状态。 不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。 Ambient sound cue: 监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

overall_soundscape:
监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。

non_diegetic_music:
稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
```

通用中文视频 WebUI 导出：

```text
镜头 26｜监控室｜4 秒｜16:9
首帧：承接拆分镜头 16，然后收回。镜头聚焦于那只手完成放置并确认的动作
镜头：极特写，固定机位，转场 fade to black
动作时间线：
- 0.00-0.80s：承接拆分镜头 16，然后收回。镜头聚焦于那只手完成放置并确认的动作
- 0.80-3.00s：然后收回。镜头聚焦于那只手完成放置并确认的动作
- 3.00-4.00s：手收回，照片静止在台面上。回放画面显示，“林小夏”即将抬起头。镜头聚焦于那只手完成放置并确认的动作。
结束落点：手收回，照片静止在台面上。回放画面显示，“林小夏”即将抬起头。镜头聚焦于那只手完成放置并确认的动作。
连续性约束：开头承接上一镜结束状态：承接拆分镜头 16：然后收回。镜头聚焦于那只手完成放置并确认的动作。；人物身份、脸型、发型、服装、关键道具与场景布局在镜头内保持连续。；只表现当前镜头可观察到的动作变化，不新增未在导演分镜或资产中声明的主体。；场景连续性锚定为：监控室。
环境声：监控屏幕电流声、轻微电子噪点、空调低频与封闭房间的静态底噪。
配乐：稀疏、低速、低音量的悬疑氛围音，接近尾帧时轻微收束。
负面约束：不要字幕、水印、logo、分屏、四宫格或界面文字。；不要改变人物身份、服装、发型、场景布局和关键道具状态。；不要出现无法由当前镜头动作解释的突变、瞬移、额外人物或错误道具。
```
