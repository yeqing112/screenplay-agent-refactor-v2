import { useState, useCallback } from 'react'
import { useTaskRunner } from './useTaskRunner'
import { delay } from './mockData'

/* ─── Types ─── */
interface ImageModel {
  id: string
  name: string
  baseUrl: string
  apiKey: string
  modelName: string
  defaultParams: string
}

interface GeneratedImage {
  id: string
  url: string
  modelName: string
  promptType: 'zh' | 'en'
  createdAt: number
}

const DEFAULT_MODELS: ImageModel[] = [
  { id: '1', name: 'Seedream 4.5', baseUrl: 'https://api.seedream.ai/v1', apiKey: 'sk-xxx', modelName: 'seedream-4.5', defaultParams: '{"size":"1024x1024","steps":20}' },
  { id: '2', name: 'DALL-E 3', baseUrl: 'https://api.openai.com/v1', apiKey: '', modelName: 'dall-e-3', defaultParams: '{"size":"1024x1024","quality":"standard"}' },
]

/* ─── Mock image generation ─── */
async function mockGenerateImage(prompt: string, model: ImageModel): Promise<string> {
  await delay(2000 + Math.random() * 1000)
  const accent = model.id === '1' ? '#a855f7' : model.id === '2' ? '#22c55e' : '#3b82f6'
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
      <rect width="400" height="300" fill="#1e293b"/>
      <rect x="20" y="20" width="360" height="260" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1"/>
      <text x="200" y="140" fill="#64748b" font-size="14" text-anchor="middle" font-family="monospace">🖼️ 生成占位</text>
      <text x="200" y="165" fill="${accent}" font-size="11" text-anchor="middle" font-family="monospace">${model.name}</text>
    </svg>`
  )}`
}

/* ─── Image Gallery: shared per-source-name store ─── */
const imageStore = new Map<string, GeneratedImage[]>()

function getImages(key: string): GeneratedImage[] {
  return imageStore.get(key) || []
}

function addImage(key: string, img: GeneratedImage) {
  const list = imageStore.get(key) || []
  list.push(img)
  imageStore.set(key, list)
}

function removeImage(key: string, imgId: string) {
  const list = imageStore.get(key) || []
  imageStore.set(key, list.filter(x => x.id !== imgId))
}

/* ─── Panel ─── */
export default function VisualPanel({ data }: { data: any }) {
  const vs = useTaskRunner()
  const v = data.visual

  const [models, setModels] = useState<ImageModel[]>(DEFAULT_MODELS)
  const [selectedModelId, setSelectedModelId] = useState(DEFAULT_MODELS[0].id)
  const [showModelConfig, setShowModelConfig] = useState(false)
  const [showImagePrompt, setShowImagePrompt] = useState<{ title: string; prompt: string; type: 'makeup' | 'scene' | 'prop' } | null>(null)
  const [imagePreview, setImagePreview] = useState<{ url: string; modelName: string } | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const selectedModel = models.find(m => m.id === selectedModelId) || models[0]

  const handleGenerateVisuals = () => {
    vs.run([
      { label: '扫描时代规范', duration: 1500 },
      { label: '生成场景设定', duration: 2000 },
      { label: '生成道具清单', duration: 1500 },
      { label: '定妆精调', duration: 2000 },
    ])
  }

  const handleGenerateImage = async (entry: { title: string; prompt: string; type: 'makeup' | 'scene' | 'prop' }) => {
    setShowImagePrompt(entry)
    setImageLoading(true)
    setImagePreview(null)
    try {
      const url = await mockGenerateImage(entry.prompt, selectedModel)
      setImagePreview({ url, modelName: selectedModel.name })
      addImage(entry.title, {
        id: `img-${Date.now()}`,
        url,
        modelName: selectedModel.name,
        promptType: 'zh',
        createdAt: Date.now(),
      })
      setRefreshKey(k => k + 1)
    } finally {
      setImageLoading(false)
    }
  }

  const selectedPrompt = showImagePrompt

  /* ─── Image Thumbnail Gallery ─── */
  const ImageGallery = useCallback(({ sourceKey, emptyText }: { sourceKey: string; emptyText?: string }) => {
    const imgs = getImages(sourceKey)
    const [previewUrl, setPreviewUrl] = useState<string | null>(null)

    const handleDelete = (imgId: string) => {
      removeImage(sourceKey, imgId)
      setRefreshKey(k => k + 1)
    }

    if (!imgs.length) {
      return emptyText ? <div className="text-[12px] text-[#475569] mt-1.5">{emptyText}</div> : null
    }
    return (
      <>
        <div className="flex flex-wrap gap-2 mt-1.5">
          {imgs.map(img => (
            <div key={img.id} className="group relative cursor-pointer">
              <img
                src={img.url}
                alt={sourceKey}
                className="w-20 h-15 object-cover rounded border border-[#1e293b] hover:border-blue-500 transition-colors"
                onClick={() => setPreviewUrl(img.url)}
              />
              {/* Hover overlay */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/50 rounded transition-colors opacity-0 group-hover:opacity-100 flex">
                {/* Click to enlarge */}
                <button
                  onClick={(e) => { e.stopPropagation(); setPreviewUrl(img.url) }}
                  className="flex-1 flex items-center justify-center"
                  title="点击查看大图"
                >
                  <svg className="w-4 h-4 text-white/80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
                  </svg>
                </button>
                {/* Delete */}
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(img.id) }}
                  className="absolute top-0.5 right-0.5 w-4 h-4 bg-red-600/80 hover:bg-red-600 rounded-full flex items-center justify-center transition-colors"
                  title="删除此图片"
                >
                  <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
        {previewUrl && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70" onClick={() => setPreviewUrl(null)}>
            <div className="relative max-w-[80vw] max-h-[80vh]">
              <img src={previewUrl} alt={sourceKey} className="max-w-full max-h-[80vh] rounded-lg border border-[#1e293b]" onClick={e => e.stopPropagation()} />
              <button
                onClick={(e) => { e.stopPropagation(); setPreviewUrl(null) }}
                className="absolute top-2 right-2 w-6 h-6 bg-black/60 hover:bg-black/80 rounded-full flex items-center justify-center transition-colors"
              >
                <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        )}
      </>
    )
  }, [refreshKey])

  if (!v?.era) {
    return (
      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <div>
          <h1 className="text-lg font-bold text-[#f1f5f9]">🎨 视觉资产</h1>
          <p className="text-[14px] text-[#64748b] mt-1">尚未生成，点击下方按钮开始</p>
        </div>
        <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
          <div className="text-[14px] text-[#94a3b8] mb-3">基于世界观和剧本生成时代规范、场景、道具和定妆。</div>
          <button
            onClick={handleGenerateVisuals}
            disabled={vs.state === 'running'}
            className={`text-xs px-4 py-2 rounded-lg transition-colors ${
              vs.state === 'running'
                ? 'bg-amber-900/40 text-amber-400 border border-amber-800/50'
                : 'bg-purple-900/30 border border-purple-600 text-purple-400 hover:bg-purple-900/50'
            }`}
          >
            {vs.state === 'running' ? '⏳ 生成中...' : '▶️ 生成视觉设定'}
          </button>
          {vs.state === 'running' && (
            <div className="mt-3">
              <div className="h-1.5 bg-[#0f172a] rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full transition-all duration-300" style={{ width: `${Math.max(3, vs.progress)}%` }} />
              </div>
              <div className="flex justify-between text-[13px] text-[#64748b] mt-1">
                <span>{vs.step}</span>
                <span>{vs.progress}%</span>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-[#f1f5f9]">🎨 视觉资产</h1>
          <span className="text-[13px] bg-green-900/40 text-green-400 px-2 py-0.5 rounded-full">已生成</span>
        </div>
        {/* Model config */}
        <div className="flex items-center gap-2">
          <select
            value={selectedModelId}
            onChange={e => setSelectedModelId(e.target.value)}
            className="text-xs px-3 py-1.5 rounded-lg bg-[#1e293b] border border-[#334155] text-[#94a3b8] appearance-none cursor-pointer"
          >
            {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
          <button
            onClick={() => setShowModelConfig(true)}
            className="text-[11px] px-2.5 py-1.5 rounded-lg bg-[#1e293b] border border-[#334155] text-[#64748b] hover:text-[#94a3b8] transition-colors"
          >
            ⚙️ 模型配置
          </button>
        </div>
      </div>

      {/* Image generation popup */}
      {selectedPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => { setShowImagePrompt(null); setImagePreview(null) }}>
          <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5 w-[540px] max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div className="text-[14px] font-semibold text-[#e2e8f0]">🖼️ 生成图片</div>
              <button className="text-[#64748b] hover:text-[#94a3b8]" onClick={() => { setShowImagePrompt(null); setImagePreview(null) }}>✕</button>
            </div>
            <div className="mb-3">
              <div className="text-[13px] text-[#64748b] mb-1">标题：{selectedPrompt.title}</div>
            </div>
            {/* Model selector inside popup */}
            <div className="mb-3">
              <div className="text-[11px] text-[#64748b] mb-1">选择模型</div>
              <select
                value={selectedModelId}
                onChange={e => setSelectedModelId(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-lg bg-[#1e293b] border border-[#334155] text-[#94a3b8] appearance-none cursor-pointer"
              >
                {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
            <details className="mb-3" defaultChecked>
              <summary className="text-[13px] text-blue-400 cursor-pointer">📝 提示词预览</summary>
              <div className="mt-1 text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 font-mono whitespace-pre-wrap max-h-[200px] overflow-y-auto">{selectedPrompt.prompt}</div>
            </details>
            {imageLoading && (
              <div className="flex items-center justify-center h-48 bg-[#0f172a] rounded-lg border border-[#1e293b]">
                <div className="flex flex-col items-center gap-2">
                  <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                  <div className="text-[13px] text-[#64748b]">生成中...</div>
                </div>
              </div>
            )}
            {imagePreview && (
              <div className="mt-2 rounded-lg overflow-hidden border border-[#1e293b]">
                <img src={imagePreview.url} alt="generated" className="w-full h-auto" />
                <div className="text-[12px] text-[#64748b] bg-[#0a0e1a] px-3 py-1.5 text-center">由 {imagePreview.modelName} 生成（模拟占位）</div>
              </div>
            )}
            {!imageLoading && !imagePreview && (
              <button
                onClick={() => handleGenerateImage(selectedPrompt)}
                className="w-full text-xs py-2 rounded-lg bg-purple-900/30 border border-purple-600 text-purple-400 hover:bg-purple-900/50 transition-colors"
              >
                🖼️ 发送生图请求
              </button>
            )}
          </div>
        </div>
      )}

      {/* Model Config Modal */}
      {showModelConfig && (
        <ModelConfigModal models={models} onSave={m => { setModels(m); setShowModelConfig(false) }} onClose={() => setShowModelConfig(false)} />
      )}

      {/* ─── Content sections ─── */}

      {/* 1. Era Spec */}
      <details className="bg-[#111827] border border-[#1e293b] rounded-xl" defaultChecked>
        <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-5 py-3 rounded-xl hover:bg-[#1e293b] transition-colors">
          📜 时代规范
        </summary>
        <div className="px-5 pb-4 space-y-2 text-[14px] text-[#94a3b8]">
          <div><span className="text-[#64748b]">时间线：</span>{v.era.timeline_start} → {v.era.timeline_end}</div>
          <div><span className="text-[#64748b]">服饰：</span>{v.era.clothing_spec}</div>
          <div><span className="text-[#64748b]">色调：</span>{v.era.color_palette}</div>
          <div><span className="text-[#64748b]">建筑：</span>{v.era.architecture_spec}</div>
        </div>
      </details>

      {/* 2. Scene prompts (金丝雀格式) */}
      <details className="bg-[#111827] border border-[#1e293b] rounded-xl" defaultChecked>
        <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-5 py-3 rounded-xl hover:bg-[#1e293b] transition-colors">
          🏠 场景提示词（{v.locations.length}）
        </summary>
        <div className="px-5 pb-4 space-y-3">
          {(v.locations || []).map((loc: any, i: number) => (
            <details key={i} className="bg-[#0c1222] border border-[#1e293b] rounded-lg overflow-hidden">
              <summary className="text-[14px] font-medium text-[#cbd5e1] cursor-pointer px-4 py-2.5 flex items-center gap-2">
                {loc.name}
                <span className="text-[12px] text-[#64748b] font-normal">· {loc.category}</span>
              </summary>
              <div className="px-4 pb-3 space-y-2 text-[14px] text-[#94a3b8]">
                <div><span className="text-[#64748b]">风格：</span>{loc.style}</div>
                <div><span className="text-[#64748b]">描述：</span>{loc.description}</div>
                <div><span className="text-[#64748b]">色调：</span>{loc.color_palette}</div>
                <div><span className="text-[#64748b]">光影：</span>{loc.lighting_mood}</div>
                {/* EN Prompt */}
                {loc.en_prompt && (
                  <details className="mt-1">
                    <summary className="text-[13px] text-emerald-400 cursor-pointer">EN Prompt (2x2 四视图)</summary>
                    <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{loc.en_prompt}</div>
                  </details>
                )}
                {/* ZH Prompt */}
                {loc.zh_prompt && (
                  <details className="mt-1">
                    <summary className="text-[13px] text-blue-400 cursor-pointer">ZH Prompt (2x2 四视图)</summary>
                    <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{loc.zh_prompt}</div>
                  </details>
                )}
                {/* Generated images gallery */}
                <ImageGallery sourceKey={loc.name} emptyText="暂无生成图片" />
                {/* Generate image buttons */}
                <div className="flex gap-2 mt-2">
                  {loc.zh_prompt && (
                    <button
                      onClick={() => handleGenerateImage({ title: loc.name, prompt: loc.zh_prompt, type: 'scene' })}
                      className="text-xs px-3 py-1.5 rounded-lg bg-purple-900/30 border border-purple-600 text-purple-400 hover:bg-purple-900/50 transition-colors"
                    >
                      🖼️ 生图 (ZH)
                    </button>
                  )}
                  {loc.en_prompt && (
                    <button
                      onClick={() => handleGenerateImage({ title: loc.name, prompt: loc.en_prompt, type: 'scene' })}
                      className="text-xs px-3 py-1.5 rounded-lg bg-emerald-900/30 border border-emerald-600 text-emerald-400 hover:bg-emerald-900/50 transition-colors"
                    >
                      🖼️ 生图 (EN)
                    </button>
                  )}
                </div>
              </div>
            </details>
          ))}
        </div>
      </details>

      {/* 3. Prop prompts (金丝雀格式) */}
      <details className="bg-[#111827] border border-[#1e293b] rounded-xl">
        <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-5 py-3 rounded-xl hover:bg-[#1e293b] transition-colors">
          🎭 道具提示词（{v.props.length}）
        </summary>
        <div className="px-5 pb-4 space-y-2">
          {(v.props || []).map((p: any, i: number) => (
            <details key={i} className="bg-[#0c1222] border border-[#1e293b] rounded-lg overflow-hidden">
              <summary className="text-[14px] font-medium text-[#cbd5e1] cursor-pointer px-4 py-2.5 flex items-center gap-2">
                {p.name}
                <span className="text-[12px] text-[#64748b] font-normal">· {p.category} · 重要性: {p.importance || 'medium'}</span>
              </summary>
              <div className="px-4 pb-3 space-y-2 text-[14px] text-[#94a3b8]">
                <div><span className="text-[#64748b]">描述：</span>{p.description}</div>
                <div><span className="text-[#64748b]">时代：</span>{p.era || '当代'}</div>
                {/* EN Prompt */}
                {p.en_prompt && (
                  <details className="mt-1">
                    <summary className="text-[13px] text-emerald-400 cursor-pointer">EN Prompt (2x3 六视图)</summary>
                    <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{p.en_prompt}</div>
                  </details>
                )}
                {/* ZH Prompt */}
                {p.zh_prompt && (
                  <details className="mt-1">
                    <summary className="text-[13px] text-blue-400 cursor-pointer">ZH Prompt (2x3 六视图)</summary>
                    <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{p.zh_prompt}</div>
                  </details>
                )}
                {/* Generated images */}
                <ImageGallery sourceKey={p.name} emptyText="暂无生成图片" />
                {(p.en_prompt || p.zh_prompt) && (
                  <div className="flex gap-2 mt-2">
                    {p.zh_prompt && (
                      <button
                        onClick={() => handleGenerateImage({ title: p.name, prompt: p.zh_prompt, type: 'prop' })}
                        className="text-xs px-3 py-1.5 rounded-lg bg-purple-900/30 border border-purple-600 text-purple-400 hover:bg-purple-900/50 transition-colors"
                      >
                        🖼️ 生图 (ZH)
                      </button>
                    )}
                    {p.en_prompt && (
                      <button
                        onClick={() => handleGenerateImage({ title: p.name, prompt: p.en_prompt, type: 'prop' })}
                        className="text-xs px-3 py-1.5 rounded-lg bg-emerald-900/30 border border-emerald-600 text-emerald-400 hover:bg-emerald-900/50 transition-colors"
                      >
                        🖼️ 生图 (EN)
                      </button>
                    )}
                  </div>
                )}
              </div>
            </details>
          ))}
        </div>
      </details>

      {/* 4. Makeup prompts (金丝雀定妆照格式) */}
      <details className="bg-[#111827] border border-[#1e293b] rounded-xl">
        <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-5 py-3 rounded-xl hover:bg-[#1e293b] transition-colors">
          💄 定妆提示词（{v.makeups.length}）
        </summary>
        <div className="px-5 pb-4 space-y-3">
          {(() => {
            const byEp: Record<number, any[]> = {}
            ;(v.makeups || []).forEach((m: any) => {
              if (!byEp[m.episode]) byEp[m.episode] = []
              byEp[m.episode].push(m)
            })
            return Object.entries(byEp).sort(([a],[b]) => Number(a)-Number(b)).map(([ep, items]) => (
              <details key={ep} className="bg-[#0c1222] border border-[#1e293b] rounded-lg" defaultChecked>
                <summary className="text-[14px] font-medium text-[#cbd5e1] cursor-pointer px-4 py-2.5">
                  第{ep}集 · {items.length} 个角色
                </summary>
                <div className="px-4 pb-3 space-y-3">
                  {items.map((m: any, i: number) => (
                    <div key={i} className="bg-[#0a0e1a] rounded-lg p-3 border border-[#1e293b]">
                      {/* Character header */}
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <div className="text-[14px] font-medium text-[#cbd5e1]">{m.character_name}</div>
                          <div className="text-[12px] text-[#64748b] mt-0.5">{m.identity || m.makeup_spec?.slice(0, 40)}</div>
                        </div>
                      </div>
                      {/* Makeup sheet card */}
                      <div className="bg-[#080c16] rounded p-3 text-[14px] text-[#94a3b8] font-mono leading-relaxed whitespace-pre-wrap max-h-[260px] overflow-y-auto">
                        {`人物定妆设定板，展示同一个角色的六个视角。
上排为脸部特写：正面、侧面、45度；
下排为全身展示：正面、侧面、背面。
六个视角必须是同一个人，保持面部一致性、发型一致性、服装一致性、体型一致性。
人物为：【${m.identity || ''}】岁的【中国/地区】【${m.gender || '男性'}】，身份是【${m.character_name}】，气质【${m.temperament || ''}】。
外貌特征：【${m.appearance || m.makeup_spec || ''}】。
发型：【${m.hair_style || ''}】。
服装：【${m.refined_outfit || ''}】。
配饰：【${m.refined_accessories || '无'}】。
表情自然克制，站姿标准，适合影视角色建模。
角色设定板，六宫格排版，纯白或浅灰背景，统一柔和影棚布光，超写实，电影级质感，高细节，8k，专业影视定妆照风格。`}
                      </div>
                      {/* Raw visual_prompt_zh */}
                      {m.visual_prompt_zh && (
                        <details className="mt-2">
                          <summary className="text-[13px] text-blue-400 cursor-pointer">✨ 原始定妆提示词</summary>
                          <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{m.visual_prompt_zh}</div>
                        </details>
                      )}
                      {/* Generated images */}
                      <ImageGallery sourceKey={`${m.character_name} 定妆照`} emptyText="暂无生成图片" />
                      {/* Generate image buttons */}
                      <div className="flex gap-2 mt-2">
                        <button
                          onClick={() => handleGenerateImage({ title: `${m.character_name} 定妆照`, prompt: m.visual_prompt_zh || '', type: 'makeup' })}
                          className="text-xs px-3 py-1.5 rounded-lg bg-rose-900/30 border border-rose-600 text-rose-400 hover:bg-rose-900/50 transition-colors"
                        >
                          🖼️ 生图：定妆照
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            ))
          })()}
        </div>
      </details>
    </div>
  )
}

/* ─── Model Config Modal ─── */
function ModelConfigModal({
  models,
  onSave,
  onClose,
}: {
  models: ImageModel[]
  onSave: (models: ImageModel[]) => void
  onClose: () => void
}) {
  const [list, setList] = useState<ImageModel[]>(JSON.parse(JSON.stringify(models)))
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Partial<ImageModel>>({})

  const updateField = (id: string, field: string, value: string) => {
    setList(prev => prev.map(m => m.id === id ? { ...m, [field]: value } : m))
  }

  const addModel = () => {
    const id = String(Date.now())
    setList(prev => [...prev, { id, name: '新模型', baseUrl: '', apiKey: '', modelName: '', defaultParams: '{}' }])
    setEditingId(id)
  }

  const removeModel = (id: string) => {
    if (list.length <= 1) return
    setList(prev => prev.filter(m => m.id !== id))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5 w-[540px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="text-[15px] font-semibold text-[#e2e8f0]">⚙️ 生图模型配置</div>
          <button className="text-[#64748b] hover:text-[#94a3b8] text-sm" onClick={onClose}>✕</button>
        </div>

        <div className="text-[12px] text-[#64748b] mb-3">
          支持兼容 OpenAI 图像生成 API 的模型。只需填写基础 URL、API Key 和模型名。
        </div>

        <div className="space-y-3">
          {list.map((m) => (
            <div key={m.id} className="bg-[#0c1222] border border-[#1e293b] rounded-lg p-3 space-y-2">
              <div className="flex items-center justify-between">
                <input
                  className="text-[14px] font-medium text-[#e2e8f0] bg-transparent border-b border-transparent focus:border-blue-500 outline-none w-40"
                  value={m.name}
                  onChange={e => updateField(m.id, 'name', e.target.value)}
                  placeholder="模型名称"
                />
                <button className="text-xs text-red-400 hover:text-red-300" onClick={() => removeModel(m.id)}>删除</button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-[11px] text-[#64748b] mb-0.5">API 地址</div>
                  <input className="w-full text-[13px] bg-[#0a0e1a] border border-[#1e293b] rounded px-2 py-1.5 text-[#94a3b8] outline-none focus:border-blue-600" value={m.baseUrl} onChange={e => updateField(m.id, 'baseUrl', e.target.value)} placeholder="https://api.xxx.com/v1" />
                </div>
                <div>
                  <div className="text-[11px] text-[#64748b] mb-0.5">API Key</div>
                  <input className="w-full text-[13px] bg-[#0a0e1a] border border-[#1e293b] rounded px-2 py-1.5 text-[#94a3b8] outline-none focus:border-blue-600" type="password" value={m.apiKey} onChange={e => updateField(m.id, 'apiKey', e.target.value)} placeholder="sk-xxx" />
                </div>
                <div>
                  <div className="text-[11px] text-[#64748b] mb-0.5">模型名</div>
                  <input className="w-full text-[13px] bg-[#0a0e1a] border border-[#1e293b] rounded px-2 py-1.5 text-[#94a3b8] outline-none focus:border-blue-600" value={m.modelName} onChange={e => updateField(m.id, 'modelName', e.target.value)} placeholder="model-name" />
                </div>
                <div>
                  <div className="text-[11px] text-[#64748b] mb-0.5">默认参数 (JSON)</div>
                  <input className="w-full text-[13px] bg-[#0a0e1a] border border-[#1e293b] rounded px-2 py-1.5 text-[#94a3b8] outline-none focus:border-blue-600" value={m.defaultParams} onChange={e => updateField(m.id, 'defaultParams', e.target.value)} placeholder='{"size":"1024x1024"}' />
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2 mt-4">
          <button onClick={addModel} className="text-xs px-3 py-1.5 rounded-lg border border-dashed border-[#334155] text-[#64748b] hover:text-[#94a3b8] hover:border-[#475569] transition-colors">
            + 添加模型
          </button>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={onClose} className="text-xs px-4 py-1.5 rounded-lg bg-[#1e293b] text-[#64748b] hover:text-[#94a3b8] transition-colors">取消</button>
            <button onClick={() => onSave(list)} className="text-xs px-4 py-1.5 rounded-lg bg-blue-900/30 border border-blue-600 text-blue-400 hover:bg-blue-900/50 transition-colors">保存</button>
          </div>
        </div>
      </div>
    </div>
  )
}
