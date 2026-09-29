window.UI_V3_FIXTURE = {
  project: { name: '潮汐回声', meta: 'S01 · 3 集 · 42 镜头', status: '正在制作第 1 集' },
  episode: { label: '第 1 集', title: '雨夜来信', shots: 18, completed: 8, review: 3, generating: 2, waiting: 3, blocked: 2 },
  shots: [
    { id: '214', scene: '医院走廊', duration: '5s', state: 'review', label: '待你审核关键帧方案', tone: 'violet', stage: '关键帧' },
    { id: '215', scene: '病房', duration: '6s', state: 'waiting', label: '等待上游', tone: 'amber', stage: '导演' },
    { id: '216', scene: '病房门口', duration: '4s', state: 'image', label: '图片候选待审核', tone: 'blue', stage: '图片' },
    { id: '217', scene: '走廊转身', duration: '5s', state: 'video', label: '视频候选待审核', tone: 'cyan', stage: '视频' },
    { id: '218', scene: '楼梯间', duration: '4s', state: 'complete', label: '已确认为正式版本', tone: 'green', stage: '完成' },
    { id: '219', scene: '电梯前', duration: '5s', state: 'stale', label: '上游内容已更新', tone: 'rose', stage: '关键帧' }
  ],
  reviews: [
    { id: 'r1', type: '关键帧审核', shot: '214', scene: '医院走廊', reason: '确认 START → MIDDLE → END 的动作和情绪变化', recommendation: '建议保留缓慢推进，让迟疑转为紧张。', version: 'v03', preview: 'keyframe' },
    { id: 'r2', type: '图片审核', shot: '216', scene: '病房门口', reason: '选择最符合人物身份的图片候选', recommendation: '候选 B 的人物轮廓与正式资产更一致。', version: 'v02', preview: 'image' },
    { id: 'r3', type: '视频审核', shot: '217', scene: '走廊转身', reason: '确认转身动作与 START / END 连续性', recommendation: '候选 A 的结尾停顿更接近镜头意图。', version: 'v01', preview: 'video' },
    { id: 'r4', type: '导演审核', shot: '215', scene: '病房', reason: '场景空间和人物视线等待上游确认', recommendation: '等待正式场景资产后继续。', version: 'v04', preview: 'director' }
  ]
};
