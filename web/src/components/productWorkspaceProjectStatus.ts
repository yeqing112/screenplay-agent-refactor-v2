const PROJECT_STATUS_LABELS: Record<string, string> = {
  draft: '待启动',
  created: '项目已创建',
  imported: '已导入原文',
  ingested: '已完成切章',
  read: '已完成逐章分析',
  bibled: '已完成小说圣经',
  bibeled: '已完成小说圣经',
  resolved: '已完成别名归并',
  portraited: '已完成人物设定',
  prepared: '内容已就绪',
  content_ready: '内容已就绪',
  adapting: '改编进行中',
  adapted: '改编已确认',
  outlined: '大纲已完成',
  scripting: '剧本进行中',
  scripted: '剧本已完成',
  storyboarding: '分镜进行中',
  storyboarded: '分镜已完成',
  asseting: '资产整理中',
  qa: 'QA 处理中',
  delivered: '已进入交付',
  archived: '已归档',
  error: '状态异常',
}

export function getProjectStatusLabel(status: string | null | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  return PROJECT_STATUS_LABELS[normalized] || '状态待确认'
}

export function isKnownProjectStatus(status: string | null | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  return Boolean(normalized && PROJECT_STATUS_LABELS[normalized])
}
