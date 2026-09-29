# Production UI V3 Visual Direction Prototype

这是隔离的只读视觉原型，不进入 `web/` 生产前端。

## Routes

- `direction-a/` — Cinematic Command：沉浸、媒体优先、电影制作控制台
- `direction-b/` — Editorial Studio：内容阅读、导演意图、媒体与文本平衡
- `direction-c/` — Precision Production：高密度、可扫描、面向 40+ 镜头的专业操作台

## Fixture

三个方向使用完全相同的本地 fixture：潮汐回声、3 集、42 镜头；第 1 集 18 镜头，其中 8 完成、3 待审核、2 生成中、3 等待上游、2 阻塞。核心镜头是 Shot 214 / 医院走廊 / 5s / 关键帧方案待审核。

## Prototype interactions

- 制片台 / 镜头工坊 / 待我处理导航
- Shot 选择
- Review item 选择
- START / MIDDLE / END 阶段切换
- 批准与要求修改的视觉反馈
- 生产详情抽屉
- A / R / Space 快捷键提示

所有动作只改变浏览器内存中的原型状态；backend calls、provider calls 和 database writes 均为 0。
