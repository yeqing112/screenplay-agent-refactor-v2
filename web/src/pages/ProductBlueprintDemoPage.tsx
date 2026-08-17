import { useMemo, useState } from 'react'
import {
  ArrowLeft,
  Boxes,
  CheckCircle2,
  Clapperboard,
  Compass,
  FileOutput,
  FileText,
  FolderKanban,
  Image as ImageIcon,
  LayoutDashboard,
  Library,
  ListTodo,
  Settings2,
  Sparkles,
  Upload,
  Users,
  Wrench,
} from 'lucide-react'

type DemoSection =
  | 'dashboard'
  | 'content'
  | 'adaptation'
  | 'scripts'
  | 'workbench'
  | 'assets'
  | 'qa'
  | 'tasks'
  | 'delivery'
  | 'models'

type ShotStatus = 'blocked' | 'ready' | 'review' | 'done'

interface ShotItem {
  id: string
  title: string
  beat: string
  characters: string[]
  scene: string
  props: string[]
  staticPrompt: string
  motionPrompt: string
  references: { kind: string; name: string; status: 'ready' | 'missing' }[]
  imageVersions: number
  videoVersions: number
  qaIssues: number
  status: ShotStatus
}

const contentSources = [
  {
    title: '上传长篇小说',
    description: '支持 txt / markdown / doc 文本导入，自动切章、统计字数、识别人物与主线冲突。',
    action: '上传文件',
    notes: ['适合已完结长篇', '自动章节切分', '进入内容清洗与切章确认'],
  },
  {
    title: '添加短篇小说',
    description: '支持直接粘贴短篇全文、段落录入或一次录入多则短篇，用于单集或少集改编。',
    action: '新建短篇',
    notes: ['适合 3k-30k 字短篇', '可手动补标题/标签', '支持立即进入改编方向评估'],
  },
  {
    title: '内容整理台',
    description: '用于处理上传后的原文清洗、章节合并、短篇拆段、版本备注和素材状态标记。',
    action: '打开整理台',
    notes: ['清洗原文噪音', '确认章节边界', '标记可改编版本'],
  },
]

const adaptationOptions = [
  {
    name: '竖屏情绪悬疑短剧',
    audience: '25-45 岁女性',
    hook: '危险关系中的情绪试探与真相反转',
    strength: '中改',
    rhythm: '强钩子、高停顿、高情绪拉扯',
    keep: '人物关系核心、天台相遇、危险感',
    enhance: '每集结尾钩子、误导信息、动作切点',
  },
  {
    name: '都市关系流连续短片',
    audience: '18-30 岁女性',
    hook: '两个人逐步靠近又互相提防的暧昧危险感',
    strength: '低改',
    rhythm: '情绪递进、气氛优先、事件适中',
    keep: '原文氛围、人物对视、心理压迫感',
    enhance: '对白张力、人物意图外显、视觉符号',
  },
  {
    name: '强反转剧情向短剧',
    audience: '大众短剧用户',
    hook: '每集一个关系反转，强化爽点与误判',
    strength: '高改',
    rhythm: '快节奏、强转场、强信息差',
    keep: '核心设定和主人物',
    enhance: '冲突密度、反转频率、外部事件',
  },
]

const demoEpisodes = [
  { id: 1, title: '第 1 集', progress: 82, blockers: 2, readyShots: 9, totalShots: 12, status: '分镜修订中' },
  { id: 2, title: '第 2 集', progress: 56, blockers: 5, readyShots: 6, totalShots: 14, status: '资产补齐中' },
  { id: 3, title: '第 3 集', progress: 24, blockers: 7, readyShots: 2, totalShots: 11, status: '剧本已完成' },
]

const demoScriptEpisodes = [
  {
    id: 1,
    title: '第 1 集',
    premise: '姐姐和阿宁在旧楼天台第一次正面相遇，情绪线从试探走向危险。',
    scriptStatus: '已定稿',
    qaStatus: '1 个待关闭问题',
    shots: 12,
    lineCount: 38,
  },
  {
    id: 2,
    title: '第 2 集',
    premise: '阿宁开始怀疑姐姐的真实目的，楼道追逐成为情绪爆点。',
    scriptStatus: '待润色',
    qaStatus: '3 个脚本问题',
    shots: 14,
    lineCount: 42,
  },
  {
    id: 3,
    title: '第 3 集',
    premise: '姐姐的过往被撕开，人物关系正式反转。',
    scriptStatus: '大纲完成',
    qaStatus: '未进入分镜',
    shots: 11,
    lineCount: 0,
  },
]

const scriptWorkbench = {
  title: '第 1 集剧本工作台',
  summary: '目标是把小说片段整理为可分镜化的单集剧本，并在进入分镜前完成脚本级质检。',
  leftOutline: [
    '剧情目标：完成姐姐和阿宁第一次对峙',
    '人物任务：建立姐姐的危险感，建立阿宁的观察视角',
    '情绪节奏：克制 -> 停顿 -> 悬疑上扬',
    '分镜准备：关键场景已经锁定为“旧楼天台夜景”',
  ],
  scenes: [
    { id: 'SC-1', name: '旧楼天台入口', purpose: '阿宁上楼，听见打火机声音，建立疑虑。', status: '已完成' },
    { id: 'SC-2', name: '天台对峙', purpose: '姐姐回头，二人第一次正面相遇。', status: '已完成' },
    { id: 'SC-3', name: '火光特写', purpose: '用道具细节承接危险感并给分镜提供切点。', status: '待优化' },
  ],
  scriptExcerpt: [
    '阿宁推开通往天台的铁门，门轴发出短促而刺耳的摩擦声。',
    '风迎面扑来，带着水泥墙体和铁锈混合的潮冷气味。',
    '不远处，一个女人站在栏杆边，手里那点火光明明灭灭，像在等人，又像在犹豫什么。',
    '阿宁停住脚步，没有立刻开口。',
    '女人缓慢转身，视线越过风声落到她脸上。',
  ],
  checks: [
    { name: '单集目标清晰', status: '通过' },
    { name: '人物情绪递进明确', status: '通过' },
    { name: '对话可分镜化', status: '通过' },
    { name: '镜头切点充分', status: '待加强' },
  ],
}

const demoShots: ShotItem[] = [
  {
    id: '1-01',
    title: '天台初见',
    beat: '姐姐第一次在天台看见阿宁，气氛克制但危险。',
    characters: ['姐姐·城市便装', '阿宁·校服版'],
    scene: '旧楼天台夜景',
    props: ['旧手机', '防风打火机'],
    staticPrompt: '夜间旧楼天台，冷白城市边缘光，姐姐站在栏杆边侧身回望，阿宁停在门口，二人保持距离，真实都市质感，电影级中景构图。',
    motionPrompt: '镜头从阿宁肩后缓慢推进到姐姐半身，风吹动衣角，二人短暂停顿后对视，节奏克制，保留悬念。',
    references: [
      { kind: '人物', name: '姐姐·城市便装', status: 'ready' },
      { kind: '人物', name: '阿宁·校服版', status: 'ready' },
      { kind: '场景', name: '旧楼天台夜景', status: 'ready' },
      { kind: '道具', name: '旧手机', status: 'missing' },
    ],
    imageVersions: 3,
    videoVersions: 2,
    qaIssues: 1,
    status: 'review',
  },
  {
    id: '1-02',
    title: '打火机特写',
    beat: '用道具细节承接危险感。',
    characters: ['姐姐·城市便装'],
    scene: '旧楼天台夜景',
    props: ['防风打火机'],
    staticPrompt: '手部特写，旧式金属打火机在风中亮起，指节紧绷，冷色反光，背景虚化成城市霓虹散景。',
    motionPrompt: '极近景轻微横移，火苗亮起后停顿半秒，再切到姐姐眼神，强调情绪递进。',
    references: [
      { kind: '人物', name: '姐姐·城市便装', status: 'ready' },
      { kind: '场景', name: '旧楼天台夜景', status: 'ready' },
      { kind: '道具', name: '防风打火机', status: 'ready' },
    ],
    imageVersions: 2,
    videoVersions: 1,
    qaIssues: 0,
    status: 'ready',
  },
  {
    id: '1-03',
    title: '阿宁反应镜头',
    beat: '阿宁意识到姐姐情绪不对，气氛陡然收紧。',
    characters: ['阿宁·校服版'],
    scene: '旧楼天台夜景',
    props: [],
    staticPrompt: '阿宁半身近景，风吹乱发丝，表情从试探转向紧张，背景是微亮的门口与远处城市光点。',
    motionPrompt: '轻微推近到眼神停顿，呼吸感镜头，不做夸张运动，重点是情绪变化。',
    references: [
      { kind: '人物', name: '阿宁·校服版', status: 'ready' },
      { kind: '场景', name: '旧楼天台夜景', status: 'ready' },
    ],
    imageVersions: 1,
    videoVersions: 0,
    qaIssues: 2,
    status: 'blocked',
  },
]

const assetGroups = {
  characters: [
    { name: '姐姐·城市便装', type: '人物定妆', variants: 3, linkedShots: 8, status: '已就绪' },
    { name: '阿宁·校服版', type: '人物定妆', variants: 2, linkedShots: 6, status: '已就绪' },
    { name: '姐姐·雨夜外套版', type: '人物变体', variants: 1, linkedShots: 2, status: '待补参考图' },
  ],
  locations: [
    { name: '旧楼天台夜景', type: '场景', variants: 2, linkedShots: 11, status: '已就绪' },
    { name: '楼道转角', type: '场景', variants: 1, linkedShots: 4, status: '待补参考图' },
  ],
  props: [
    { name: '旧手机', type: '道具', variants: 1, linkedShots: 5, status: '缺参考图' },
    { name: '防风打火机', type: '道具', variants: 2, linkedShots: 3, status: '已就绪' },
  ],
}

const qaIssues = [
  { id: 'QA-101', level: '中', title: '脚本场次 SC-3 切点不足', action: '补强场次动作节点', owner: '编剧', status: '待修复' },
  { id: 'QA-201', level: '高', title: '镜头 1-03 人物表情偏差', action: '重编译静态提示词', owner: '分镜编辑', status: '待修复' },
  { id: 'QA-202', level: '中', title: '镜头 1-01 缺少旧手机参考图', action: '补生成道具参考图', owner: '美术执行', status: '处理中' },
]

const taskQueue = [
  { id: 'TASK-301', type: '原文切章确认', target: '《天台之后》导入稿', status: 'done', progress: '已完成' },
  { id: 'TASK-401', type: '改编方向评估', target: '生成 3 个候选方向', status: 'done', progress: '已锁定主方向' },
  { id: 'TASK-701', type: '批量编译提示词', target: '第 1 集 12 个镜头', status: 'running', progress: '8 / 12' },
  { id: 'TASK-703', type: '视频重生成', target: '镜头 1-02', status: 'error', progress: '模型返回超时，可重试' },
]

const modelMatrix = [
  { kind: '文本编译', provider: 'OpenAI Compatible / Ollama', model: 'gemma4:12b', refs: '文本摘要', async: '否' },
  { kind: '图像生成', provider: 'PoYo', model: 'gpt-image-2 / nano-banana-2', refs: '多参考图', async: '是' },
  { kind: '视频生成', provider: 'PoYo', model: 'seedance-2 / kling-3-api', refs: '分镜图 + 运动提示词', async: '是' },
]

function sectionTitle(section: DemoSection): string {
  switch (section) {
    case 'dashboard':
      return '项目控制台'
    case 'content':
      return '内容准备'
    case 'adaptation':
      return '改编方向'
    case 'scripts':
      return '剧本工作台'
    case 'workbench':
      return '镜头工作台'
    case 'assets':
      return '资产中心'
    case 'qa':
      return 'QA 修复工作台'
    case 'tasks':
      return '任务中心'
    case 'delivery':
      return '导出中心'
    case 'models':
      return '模型管理'
  }
}

function statusPill(status: ShotStatus) {
  if (status === 'done') return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
  if (status === 'ready') return 'bg-sky-500/15 text-sky-300 border-sky-500/30'
  if (status === 'review') return 'bg-amber-500/15 text-amber-300 border-amber-500/30'
  return 'bg-rose-500/15 text-rose-300 border-rose-500/30'
}

const sections: { id: DemoSection; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'dashboard', label: '项目控制台', icon: LayoutDashboard },
  { id: 'content', label: '内容准备', icon: Library },
  { id: 'adaptation', label: '改编方向', icon: Compass },
  { id: 'scripts', label: '剧本工作台', icon: FileText },
  { id: 'workbench', label: '镜头工作台', icon: Clapperboard },
  { id: 'assets', label: '资产中心', icon: Boxes },
  { id: 'qa', label: 'QA 修复', icon: Wrench },
  { id: 'tasks', label: '任务中心', icon: ListTodo },
  { id: 'delivery', label: '导出中心', icon: FileOutput },
  { id: 'models', label: '模型管理', icon: Settings2 },
]

function Card({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-4">
      <div className="text-xs text-slate-400">{title}</div>
      <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{detail}</div>
    </div>
  )
}

export default function ProductBlueprintDemoPage({ onBack }: { onBack: () => void }) {
  const [section, setSection] = useState<DemoSection>('dashboard')
  const [selectedEpisode, setSelectedEpisode] = useState(1)
  const [selectedShotId, setSelectedShotId] = useState('1-01')

  const selectedShot = useMemo(
    () => demoShots.find((shot) => shot.id === selectedShotId) ?? demoShots[0],
    [selectedShotId],
  )

  return (
    <div className="h-full bg-slate-950 text-slate-200">
      <div className="flex h-full">
        <aside className="w-64 border-r border-slate-800 bg-slate-950 p-4">
          <button
            onClick={onBack}
            className="mb-4 flex items-center gap-2 rounded-lg border border-slate-800 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-700 hover:bg-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            返回项目列表
          </button>

          <div className="rounded-xl border border-violet-500/20 bg-violet-500/10 p-4">
            <div className="text-xs uppercase tracking-[0.2em] text-violet-300/80">Prototype Demo</div>
            <div className="mt-2 text-lg font-semibold text-white">AI 短剧生产操作系统</div>
            <div className="mt-2 text-sm leading-6 text-slate-300">
              从内容准备、改编方向、剧本、分镜、资产到 QA 和交付，把完整产品结构一次摆清楚。
            </div>
          </div>

          <nav className="mt-6 space-y-1">
            {sections.map((item) => {
              const Icon = item.icon
              const active = section === item.id
              return (
                <button
                  key={item.id}
                  onClick={() => setSection(item.id)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                    active ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              )
            })}
          </nav>

          <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="flex items-center gap-2 text-sm text-white">
              <FolderKanban className="h-4 w-4 text-sky-300" />
              当前演示项目
            </div>
            <div className="mt-3 text-sm text-slate-300">《天台之后》</div>
            <div className="mt-2 text-xs leading-6 text-slate-500">
              已导入原文，已锁定改编方向，剧本完成 1 集，分镜和资产仍在推进。
            </div>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto">
          <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/95 px-6 py-4 backdrop-blur">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Blueprint Section</div>
                <h1 className="mt-1 text-2xl font-semibold text-white">{sectionTitle(section)}</h1>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-300">
                  演示数据
                </span>
                <span className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-400">
                  前端原型
                </span>
              </div>
            </div>
          </header>

          <div className="px-6 py-6">
            {section === 'dashboard' && (
              <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
                  <Card title="内容准备" value="已完成" detail="长篇上传和切章确认完成" />
                  <Card title="改编方向" value="已锁定" detail="主方向为竖屏情绪悬疑短剧" />
                  <Card title="剧本阶段" value="1 / 3 集" detail="第 1 集定稿，第 2 集待润色" />
                  <Card title="分镜阶段" value="68%" detail="镜头编译与出图正在推进" />
                  <Card title="QA 阻塞" value="3" detail="脚本 1 个，分镜 2 个" />
                  <Card title="可导出集数" value="1 / 3" detail="仅第 1 集接近交付状态" />
                </div>

                <div className="grid gap-6 xl:grid-cols-[1.35fr,0.9fr]">
                  <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                    <div className="flex items-center gap-2 text-white">
                      <Library className="h-4 w-4 text-sky-300" />
                      主链路阶段看板
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-6">
                      {([
                        ['内容准备', '已完成', 'content'],
                        ['改编方向', '已锁定', 'adaptation'],
                        ['剧本', '进行中', 'scripts'],
                        ['分镜', '进行中', 'workbench'],
                        ['资产', '待补齐', 'assets'],
                        ['导出', '未放行', 'delivery'],
                      ] as const).map(([name, value, target]) => (
                        <button
                          key={name}
                          onClick={() => setSection(target)}
                          className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-left transition hover:border-slate-700"
                        >
                          <div className="text-sm font-medium text-white">{name}</div>
                          <div className="mt-2 text-xs text-slate-400">{value}</div>
                        </button>
                      ))}
                    </div>

                    <div className="mt-5 space-y-4">
                      {demoEpisodes.map((episode) => (
                        <button
                          key={episode.id}
                          onClick={() => {
                            setSelectedEpisode(episode.id)
                            setSection('workbench')
                          }}
                          className="w-full rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-left transition hover:border-slate-700"
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="text-sm font-medium text-white">{episode.title}</div>
                              <div className="mt-1 text-xs text-slate-500">{episode.status}</div>
                            </div>
                            <div className="text-xs text-slate-400">
                              Ready {episode.readyShots}/{episode.totalShots}
                            </div>
                          </div>
                          <div className="mt-3 h-2 rounded-full bg-slate-800">
                            <div className="h-2 rounded-full bg-sky-400" style={{ width: `${episode.progress}%` }} />
                          </div>
                          <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                            <span>进度 {episode.progress}%</span>
                            <span>阻塞 {episode.blockers}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </section>

                  <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                    <div className="flex items-center gap-2 text-white">
                      <Sparkles className="h-4 w-4 text-violet-300" />
                      下一步建议动作
                    </div>
                    <div className="mt-4 space-y-3 text-sm">
                      {[
                        '内容准备页需要同时支持“上传长篇”和“新建短篇”两种入口，不然起点不完整。',
                        '改编方向已锁定后，剧本生成和分镜编译都必须继承相同的节奏、受众和卖点约束。',
                        '先补强第 1 集脚本中的“火光特写”切点，再继续镜头 1-02 的视频重生成。',
                      ].map((tip) => (
                        <div key={tip} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-slate-300">
                          {tip}
                        </div>
                      ))}
                    </div>
                  </section>
                </div>
              </div>
            )}

            {section === 'content' && (
              <div className="grid gap-6 xl:grid-cols-[1.1fr,1.1fr,0.9fr]">
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center gap-2 text-white">
                    <Upload className="h-4 w-4 text-sky-300" />
                    内容入口
                  </div>
                  <div className="mt-4 space-y-3">
                    {contentSources.map((item) => (
                      <div key={item.title} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-medium text-white">{item.title}</div>
                          <button className="rounded-md border border-slate-800 px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-700">
                            {item.action}
                          </button>
                        </div>
                        <div className="mt-2 text-sm leading-6 text-slate-400">{item.description}</div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {item.notes.map((note) => (
                            <span key={note} className="rounded-full border border-slate-800 px-2 py-1 text-[11px] text-slate-400">
                              {note}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">内容整理台</div>
                  <div className="mt-4 grid gap-3">
                    {[
                      ['原文版本', '《天台之后》上传稿 v2'],
                      ['内容形态', '中篇小说，12 章'],
                      ['切章状态', '已确认章节边界'],
                      ['短篇支持', '可直接粘贴新建，不必先上传文件'],
                      ['进入改编方向', '已具备评估条件'],
                    ].map(([name, value]) => (
                      <div key={name} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 px-4 py-3 text-sm">
                        <span className="text-slate-300">{name}</span>
                        <span className="text-white">{value}</span>
                      </div>
                    ))}
                  </div>

                  <div className="mt-5 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                    正式版里，这里应接入：文件上传、粘贴录入、章节切分确认、短篇拆段、版本备注、原文清洗和基础内容质检。
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">为什么内容准备必须单独存在</div>
                  <div className="mt-4 space-y-3 text-sm text-slate-300">
                    {[
                      '小说来源并不只有“长篇上传”，还包括短篇直录和临时素材整理。',
                      '内容准备决定后续切章、节奏、角色抽取和改编方向评估质量。',
                      '如果入口不清晰，后面的剧本和分镜都会建立在脏数据上。',
                    ].map((item) => (
                      <div key={item} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        {item}
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {section === 'adaptation' && (
              <div className="grid gap-6 xl:grid-cols-[1.2fr,0.9fr]">
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center gap-2 text-white">
                    <Compass className="h-4 w-4 text-violet-300" />
                    改编方向候选
                  </div>
                  <div className="mt-4 space-y-4">
                    {adaptationOptions.map((option, index) => (
                      <div key={option.name} className={`rounded-xl border p-4 ${index === 0 ? 'border-violet-500/40 bg-violet-500/10' : 'border-slate-800 bg-slate-950/50'}`}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-white">{option.name}</div>
                            <div className="mt-1 text-xs text-slate-400">目标受众：{option.audience}</div>
                          </div>
                          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                            {index === 0 ? '当前选中' : '候选方案'}
                          </span>
                        </div>
                        <div className="mt-3 grid gap-2 text-sm text-slate-300 md:grid-cols-2">
                          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">一句话卖点：{option.hook}</div>
                          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">改编强度：{option.strength}</div>
                          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">节奏策略：{option.rhythm}</div>
                          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">保留内容：{option.keep}</div>
                        </div>
                        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-sm text-slate-300">
                          必须强化：{option.enhance}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">项目级锁定规则</div>
                  <div className="mt-4 space-y-3 text-sm text-slate-300">
                    {[
                      '改编方向确定后，剧本生成、分镜编译、视觉资产风格都必须继承同一套约束。',
                      '后续如需改方向，应产生新版本，而不是覆盖旧项目基线。',
                      '系统应支持先给 2-3 个候选，再由用户选择主方向并锁定。',
                    ].map((item) => (
                      <div key={item} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        {item}
                      </div>
                    ))}
                  </div>

                  <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                    <div className="text-sm font-medium text-white">当前锁定结果</div>
                    <div className="mt-3 grid gap-2 text-sm">
                      {[
                        ['目标赛道', '竖屏情绪悬疑短剧'],
                        ['目标受众', '25-45 岁女性'],
                        ['改编强度', '中改'],
                        ['每集策略', '钩子更强、停顿更准、情绪更外显'],
                      ].map(([name, value]) => (
                        <div key={name} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                          <span className="text-slate-300">{name}</span>
                          <span className="text-white">{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
              </div>
            )}

            {section === 'scripts' && (
              <div className="grid gap-6 xl:grid-cols-[0.95fr,1.2fr,0.95fr]">
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
                  <div className="text-sm font-medium text-white">分集剧本列表</div>
                  <div className="mt-4 space-y-3">
                    {demoScriptEpisodes.map((episode) => (
                      <div key={episode.id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-white">{episode.title}</div>
                            <div className="mt-1 text-xs text-slate-500">{episode.scriptStatus}</div>
                          </div>
                          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                            {episode.shots} 镜
                          </span>
                        </div>
                        <div className="mt-3 text-xs leading-6 text-slate-400">{episode.premise}</div>
                        <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
                          <span>{episode.qaStatus}</span>
                          <span>{episode.lineCount > 0 ? `${episode.lineCount} 行台词/旁白` : '待写剧本'}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-lg font-semibold text-white">{scriptWorkbench.title}</div>
                  <div className="mt-2 text-sm text-slate-400">{scriptWorkbench.summary}</div>

                  <div className="mt-5 grid gap-4 md:grid-cols-2">
                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                      <div className="text-sm font-medium text-white">单集目标与节奏</div>
                      <div className="mt-3 space-y-2 text-sm text-slate-300">
                        {scriptWorkbench.leftOutline.map((item) => (
                          <div key={item} className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                            {item}
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                      <div className="text-sm font-medium text-white">脚本片段</div>
                      <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                        {scriptWorkbench.scriptExcerpt.map((line) => (
                          <div key={line} className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                            {line}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="mt-5 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                    正式版里，这里应接入：剧本版本树、脚本 QA、重写建议、人物情绪线检查、分镜切点推荐、剧本锁稿与放行。
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">场次与检查项</div>
                  <div className="mt-4 space-y-3">
                    {scriptWorkbench.scenes.map((scene) => (
                      <div key={scene.id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-white">{scene.name}</div>
                            <div className="mt-1 text-xs text-slate-500">{scene.id}</div>
                          </div>
                          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                            {scene.status}
                          </span>
                        </div>
                        <div className="mt-3 text-sm text-slate-300">{scene.purpose}</div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                    <div className="text-sm font-medium text-white">进入分镜前检查</div>
                    <div className="mt-3 space-y-2 text-sm">
                      {scriptWorkbench.checks.map((item) => (
                        <div key={item.name} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                          <span className="text-slate-300">{item.name}</span>
                          <span className={item.status === '通过' ? 'text-emerald-300' : 'text-amber-300'}>
                            {item.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
              </div>
            )}

            {section === 'workbench' && (
              <div className="grid gap-6 xl:grid-cols-[0.9fr,1.25fr,0.95fr]">
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-white">第 {selectedEpisode} 集镜头列表</div>
                    <button onClick={() => setSection('dashboard')} className="text-xs text-slate-400 hover:text-slate-200">
                      回看总览
                    </button>
                  </div>
                  <div className="mt-4 space-y-3">
                    {demoShots.map((shot) => (
                      <button
                        key={shot.id}
                        onClick={() => setSelectedShotId(shot.id)}
                        className={`w-full rounded-xl border p-3 text-left transition ${
                          selectedShotId === shot.id
                            ? 'border-sky-500/40 bg-sky-500/10'
                            : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-white">{shot.id}</div>
                            <div className="mt-1 text-xs text-slate-500">{shot.title}</div>
                          </div>
                          <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusPill(shot.status)}`}>
                            {shot.status}
                          </span>
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-slate-500">
                          <span>参考图 {shot.references.filter((r) => r.status === 'ready').length}/{shot.references.length}</span>
                          <span>图版 {shot.imageVersions}</span>
                          <span>视频 {shot.videoVersions}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-lg font-semibold text-white">{selectedShot.id} {selectedShot.title}</div>
                      <div className="mt-1 text-sm text-slate-400">{selectedShot.beat}</div>
                    </div>
                    <span className={`rounded-full border px-2.5 py-1 text-xs ${statusPill(selectedShot.status)}`}>
                      {selectedShot.status}
                    </span>
                  </div>

                  <div className="mt-5 grid gap-4 md:grid-cols-3">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="flex items-center gap-2 text-xs text-slate-400"><Users className="h-4 w-4" />人物引用</div>
                      <div className="mt-2 text-sm text-white">{selectedShot.characters.join(' / ')}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="flex items-center gap-2 text-xs text-slate-400"><ImageIcon className="h-4 w-4" />场景引用</div>
                      <div className="mt-2 text-sm text-white">{selectedShot.scene}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                      <div className="flex items-center gap-2 text-xs text-slate-400"><Boxes className="h-4 w-4" />道具引用</div>
                      <div className="mt-2 text-sm text-white">{selectedShot.props.join(' / ') || '无'}</div>
                    </div>
                  </div>

                  <div className="mt-5 grid gap-4 lg:grid-cols-2">
                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                      <div className="text-sm font-medium text-white">静态提示词</div>
                      <div className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                        {selectedShot.staticPrompt}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                      <div className="text-sm font-medium text-white">运动提示词</div>
                      <div className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                        {selectedShot.motionPrompt}
                      </div>
                    </div>
                  </div>

                  <div className="mt-5 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                    正式版里，这里应继续接入：引用资产选择器、prompt version 列表、锁定版本、重编译、手动修订、QA 回退记录。
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">镜头状态与操作</div>
                  <div className="mt-4 space-y-3">
                    {selectedShot.references.map((ref) => (
                      <div key={`${ref.kind}-${ref.name}`} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        <div className="flex items-center justify-between">
                          <div className="text-sm text-white">{ref.kind} · {ref.name}</div>
                          <span className={`text-xs ${ref.status === 'ready' ? 'text-emerald-300' : 'text-rose-300'}`}>
                            {ref.status === 'ready' ? '已就绪' : '缺失'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-5 grid gap-3">
                    {[
                      '补齐参考图',
                      '重编译静态提示词',
                      '重编译运动提示词',
                      '生成分镜图',
                      '生成分镜视频',
                      '送入 QA 修复',
                    ].map((action) => (
                      <button key={action} className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-left text-sm text-slate-300 hover:border-slate-700 hover:text-white">
                        {action}
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {section === 'assets' && (
              <div className="grid gap-6 xl:grid-cols-3">
                {[
                  { title: '人物资产', icon: Users, rows: assetGroups.characters },
                  { title: '场景资产', icon: ImageIcon, rows: assetGroups.locations },
                  { title: '道具资产', icon: Boxes, rows: assetGroups.props },
                ].map((group) => {
                  const Icon = group.icon
                  return (
                    <section key={group.title} className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                      <div className="flex items-center gap-2 text-white">
                        <Icon className="h-4 w-4 text-sky-300" />
                        {group.title}
                      </div>
                      <div className="mt-4 space-y-3">
                        {group.rows.map((row) => (
                          <div key={row.name} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="text-sm font-medium text-white">{row.name}</div>
                                <div className="mt-1 text-xs text-slate-500">{row.type}</div>
                              </div>
                              <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{row.status}</span>
                            </div>
                            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
                              <span>版本 {row.variants}</span>
                              <span>关联镜头 {row.linkedShots}</span>
                            </div>
                            <div className="mt-3 flex gap-2 text-xs">
                              <button className="rounded-md border border-slate-800 px-2.5 py-1.5 text-slate-300 hover:border-slate-700">预览</button>
                              <button className="rounded-md border border-slate-800 px-2.5 py-1.5 text-slate-300 hover:border-slate-700">生成参考图</button>
                              <button className="rounded-md border border-slate-800 px-2.5 py-1.5 text-slate-300 hover:border-slate-700">查看关联镜头</button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )
                })}
              </div>
            )}

            {section === 'qa' && (
              <div className="grid gap-6 xl:grid-cols-[1.2fr,0.9fr]">
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center gap-2 text-white">
                    <Wrench className="h-4 w-4 text-amber-300" />
                    问题队列
                  </div>
                  <div className="mt-4 space-y-3">
                    {qaIssues.map((issue) => (
                      <div key={issue.id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-white">{issue.title}</div>
                            <div className="mt-1 text-xs text-slate-500">{issue.id} · {issue.owner}</div>
                          </div>
                          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                            {issue.level}优先级
                          </span>
                        </div>
                        <div className="mt-3 text-sm text-slate-300">推荐修复动作：{issue.action}</div>
                        <div className="mt-3 flex gap-2 text-xs">
                          <button className="rounded-md border border-slate-800 px-2.5 py-1.5 text-slate-300 hover:border-slate-700">转修复任务</button>
                          <button className="rounded-md border border-slate-800 px-2.5 py-1.5 text-slate-300 hover:border-slate-700">打开关联对象</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center gap-2 text-white">
                    <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                    修复闭环说明
                  </div>
                  <div className="mt-4 space-y-3 text-sm text-slate-300">
                    {[
                      '脚本 QA 和分镜 QA 都要有独立问题类型，但进入统一修复工作流。',
                      '问题必须关联镜头、prompt version、资产版本或脚本场次。',
                      '修复动作要可直接执行，不能只给抽象建议。',
                    ].map((item) => (
                      <div key={item} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        {item}
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {section === 'tasks' && (
              <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-4">
                  <Card title="内容任务" value="1" detail="短篇/长篇整理结果已落盘" />
                  <Card title="方向任务" value="1" detail="改编方向评估已完成" />
                  <Card title="执行中" value="1" detail="批量编译提示词正在推进" />
                  <Card title="失败待处理" value="1" detail="视频生成超时，需要人工重试" />
                </div>
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center gap-2 text-white">
                    <ListTodo className="h-4 w-4 text-sky-300" />
                    统一任务视角
                  </div>
                  <div className="mt-4 space-y-3">
                    {taskQueue.map((task) => (
                      <div key={task.id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-white">{task.type}</div>
                            <div className="mt-1 text-xs text-slate-500">{task.id} · {task.target}</div>
                          </div>
                          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{task.status}</span>
                        </div>
                        <div className="mt-3 text-sm text-slate-300">{task.progress}</div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {section === 'delivery' && (
              <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center gap-2 text-white">
                    <FileOutput className="h-4 w-4 text-violet-300" />
                    第 1 集交付包预检
                  </div>
                  <div className="mt-4 grid gap-3">
                    {[
                      ['内容准备状态', '已通过'],
                      ['改编方向版本', '已锁定 v1'],
                      ['剧本版本', '已就绪'],
                      ['当前采纳分镜图', '9 / 12'],
                      ['当前采纳视频', '8 / 12'],
                      ['人物/场景/道具参考图', '部分缺失'],
                    ].map(([name, value]) => (
                      <div key={name} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 px-4 py-3 text-sm">
                        <span className="text-slate-300">{name}</span>
                        <span className="text-white">{value}</span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center gap-2 text-white">
                    <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                    导出规则
                  </div>
                  <div className="mt-4 space-y-3 text-sm text-slate-300">
                    {[
                      '只导出已采纳版本，不混入历史试验稿。',
                      '导出前必须校验内容准备、改编方向、剧本、分镜和 QA 的放行状态。',
                      '交付包要包含 QA 摘要、时间戳和版本号。',
                    ].map((rule) => (
                      <div key={rule} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        {rule}
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {section === 'models' && (
              <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                <div className="flex items-center gap-2 text-white">
                  <Settings2 className="h-4 w-4 text-sky-300" />
                  模型能力矩阵
                </div>
                <div className="mt-4 overflow-hidden rounded-xl border border-slate-800">
                  <table className="min-w-full divide-y divide-slate-800 text-sm">
                    <thead className="bg-slate-950/70 text-slate-400">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium">类型</th>
                        <th className="px-4 py-3 text-left font-medium">供应商</th>
                        <th className="px-4 py-3 text-left font-medium">模型</th>
                        <th className="px-4 py-3 text-left font-medium">参考图支持</th>
                        <th className="px-4 py-3 text-left font-medium">异步任务</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800 bg-slate-900">
                      {modelMatrix.map((row) => (
                        <tr key={`${row.kind}-${row.model}`}>
                          <td className="px-4 py-3 text-white">{row.kind}</td>
                          <td className="px-4 py-3 text-slate-300">{row.provider}</td>
                          <td className="px-4 py-3 text-slate-300">{row.model}</td>
                          <td className="px-4 py-3 text-slate-300">{row.refs}</td>
                          <td className="px-4 py-3 text-slate-300">{row.async}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-4 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                  正式接入时，这里应继续扩展为：供应商适配层、能力标签、参考图传递策略、异步轮询协议、失败重试与成本统计。
                </div>
              </section>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
