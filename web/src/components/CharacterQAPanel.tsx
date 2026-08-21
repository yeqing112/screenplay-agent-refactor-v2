import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Check, Loader2, Merge, RefreshCcw, UserX, Users } from 'lucide-react'

interface Character {
  id: number
  name: string
  aliases: string[]
  gender: string
  age_range: string
  role: string
  identity: string
  personality: string
  relationships: Record<string, string>
  importance: string
  chapter_range: string
  stages: Array<{ stage_name: string; chapter_start: number; chapter_end: number }>
}

interface CharacterIssue {
  issue_type: string
  severity: string
  characters: string[]
  description: string
  suggestion: string
  auto_resolvable: boolean
  evidence: Record<string, any>
}

interface MergeCandidate {
  char_a: string
  char_b: string
  confidence: string
  reason: string
  shared_fragments: string[]
  complementary_chapters: number[]
}

interface QAResult {
  book_id: number
  total_characters: number
  issues: CharacterIssue[]
  merge_candidates: MergeCandidate[]
  gender_conflicts: CharacterIssue[]
}

interface Props {
  bookId: number
}

export default function CharacterQAPanel({ bookId }: Props) {
  const [characters, setCharacters] = useState<Character[]>([])
  const [qaResult, setQaResult] = useState<QAResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [merging, setMerging] = useState<string | null>(null)
  const [resolving, setResolving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const fetchCharacters = useCallback(async () => {
    try {
      const res = await fetch(`/api/books/${bookId}/characters`)
      if (res.ok) setCharacters(await res.json())
    } catch (e) {
      console.error('Failed to fetch characters:', e)
    }
  }, [bookId])

  const fetchQA = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/characters/qa`)
      if (res.ok) setQaResult(await res.json())
    } catch (e) {
      console.error('Failed to fetch QA:', e)
    } finally {
      setLoading(false)
    }
  }, [bookId])

  useEffect(() => {
    fetchCharacters()
    fetchQA()
  }, [fetchCharacters, fetchQA])

  const handleMerge = async (nameA: string, nameB: string) => {
    setMerging(`${nameA}-${nameB}`)
    setMessage(null)
    try {
      const res = await fetch(`/api/books/${bookId}/characters/merge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name_a: nameA, name_b: nameB }),
      })
      const data = await res.json()
      if (data.error) {
        setMessage({ type: 'error', text: data.error })
      } else {
        setMessage({ type: 'success', text: `已将「${nameB}」合并到「${data.merged_into}」` })
        fetchCharacters()
        fetchQA()
      }
    } catch (e) {
      setMessage({ type: 'error', text: '合并失败' })
    } finally {
      setMerging(null)
    }
  }

  const handleResolveAliases = async () => {
    setResolving(true)
    setMessage(null)
    try {
      const res = await fetch(`/api/books/${bookId}/characters/resolve-aliases`, { method: 'POST' })
      const data = await res.json()
      const mergedCount = Object.values(data.canonical_map as Record<string, string[]>).filter(v => v.length > 1).length
      setMessage({ type: 'success', text: `别名归并完成，${mergedCount} 组角色被合并` })
      fetchCharacters()
      fetchQA()
    } catch (e) {
      setMessage({ type: 'error', text: '别名归并失败' })
    } finally {
      setResolving(false)
    }
  }

  const handleUpdateGender = async (charId: number, gender: string) => {
    try {
      const res = await fetch(`/api/books/${bookId}/characters/${charId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gender }),
      })
      if (res.ok) {
        fetchCharacters()
        fetchQA()
      }
    } catch (e) {
      console.error('Failed to update gender:', e)
    }
  }

  const genderIcon = (g: string) => {
    if (g === '男性') return '♂'
    if (g === '女性') return '♀'
    return '?'
  }

  const severityColor = (s: string) => {
    if (s === 'high') return 'text-red-400 bg-red-500/10 border-red-500/30'
    if (s === 'medium') return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
    return 'text-slate-400 bg-slate-500/10 border-slate-500/30'
  }

  const confidenceColor = (c: string) => {
    if (c === 'high') return 'text-green-400'
    if (c === 'medium') return 'text-yellow-400'
    return 'text-slate-400'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">人物画像质检</h2>
          <p className="mt-1 text-sm text-slate-400">
            检测重复角色、性别冲突、孤立 profile 等问题
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleResolveAliases}
            disabled={resolving}
            className="flex items-center gap-1.5 rounded-lg border border-slate-600 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-400 hover:text-white disabled:opacity-50"
          >
            {resolving ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCcw className="h-3 w-3" />}
            重新归并别名
          </button>
          <button
            onClick={fetchQA}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-blue-600 px-3 py-1.5 text-xs text-blue-300 transition hover:border-blue-400 hover:text-white disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCcw className="h-3 w-3" />}
            重新检测
          </button>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div className={`rounded-lg border px-4 py-3 text-sm ${
          message.type === 'success'
            ? 'border-green-500/30 bg-green-500/10 text-green-300'
            : 'border-red-500/30 bg-red-500/10 text-red-300'
        }`}>
          {message.text}
        </div>
      )}

      {/* Summary */}
      {qaResult && (
        <div className="grid grid-cols-4 gap-3">
          <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3 text-center">
            <div className="text-2xl font-bold text-white">{qaResult.total_characters}</div>
            <div className="mt-1 text-xs text-slate-400">角色总数</div>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3 text-center">
            <div className="text-2xl font-bold text-red-400">{qaResult.gender_conflicts.length}</div>
            <div className="mt-1 text-xs text-slate-400">性别冲突</div>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3 text-center">
            <div className="text-2xl font-bold text-yellow-400">{qaResult.merge_candidates.length}</div>
            <div className="mt-1 text-xs text-slate-400">合并候选</div>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3 text-center">
            <div className="text-2xl font-bold text-slate-400">
              {qaResult.issues.filter(i => i.issue_type === 'orphan_profile').length}
            </div>
            <div className="mt-1 text-xs text-slate-400">孤立 profile</div>
          </div>
        </div>
      )}

      {/* Gender Conflicts */}
      {qaResult && qaResult.gender_conflicts.length > 0 && (
        <div className="space-y-2">
          <h3 className="flex items-center gap-2 text-sm font-medium text-red-300">
            <AlertTriangle className="h-4 w-4" />
            性别冲突
          </h3>
          {qaResult.gender_conflicts.map((gc, i) => (
            <div key={i} className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
              <div className="text-sm text-red-200">{gc.description}</div>
              <div className="mt-2 text-xs text-slate-400">{gc.evidence?.reason || '性别信息不一致'}</div>
              <div className="mt-2 flex gap-2">
                {gc.characters.map(name => {
                  const char = characters.find(c => c.name === name)
                  return (
                    <div key={name} className="flex items-center gap-1 text-xs text-slate-300">
                      <span>{genderIcon(char?.gender || '')} {name}</span>
                      <select
                        value={char?.gender || ''}
                        onChange={(e) => char && handleUpdateGender(char.id, e.target.value)}
                        className="rounded border border-slate-600 bg-slate-800 px-1 py-0.5 text-xs text-white"
                      >
                        <option value="">未指定</option>
                        <option value="男性">男性</option>
                        <option value="女性">女性</option>
                      </select>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Merge Candidates */}
      {qaResult && qaResult.merge_candidates.length > 0 && (
        <div className="space-y-2">
          <h3 className="flex items-center gap-2 text-sm font-medium text-yellow-300">
            <Merge className="h-4 w-4" />
            疑似重复角色（点击合并）
          </h3>
          {qaResult.merge_candidates.map((mc, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-800/50 p-3">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white">{mc.char_a}</span>
                  <span className="text-xs text-slate-500">↔</span>
                  <span className="text-sm font-medium text-white">{mc.char_b}</span>
                  <span className={`text-xs ${confidenceColor(mc.confidence)}`}>
                    ({mc.confidence === 'high' ? '高置信' : mc.confidence === 'medium' ? '中置信' : '低置信'})
                  </span>
                </div>
                <div className="mt-1 text-xs text-slate-400">{mc.reason}</div>
              </div>
              <button
                onClick={() => handleMerge(mc.char_a, mc.char_b)}
                disabled={merging === `${mc.char_a}-${mc.char_b}`}
                className="ml-3 flex items-center gap-1 rounded-lg border border-yellow-600 px-3 py-1.5 text-xs text-yellow-300 transition hover:border-yellow-400 hover:text-white disabled:opacity-50"
              >
                {merging === `${mc.char_a}-${mc.char_b}` ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Merge className="h-3 w-3" />
                )}
                合并
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Character List */}
      <div className="space-y-2">
        <h3 className="flex items-center gap-2 text-sm font-medium text-slate-300">
          <Users className="h-4 w-4" />
          所有角色（{characters.length}）
        </h3>
        <div className="space-y-1">
          {characters.map(char => (
            <div key={char.id} className="flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2">
              <div className="flex items-center gap-3">
                <span className={`text-lg ${char.gender === '男性' ? 'text-blue-400' : char.gender === '女性' ? 'text-pink-400' : 'text-slate-500'}`}>
                  {genderIcon(char.gender)}
                </span>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{char.name}</span>
                    {char.aliases.length > 0 && (
                      <span className="text-xs text-slate-500">
                        ({char.aliases.join(', ')})
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-slate-400">
                    {char.identity || '未知身份'} · {char.chapter_range || '未知章节'}
                    {char.stages.length > 0 && ` · ${char.stages.length} 阶段`}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-xs ${
                  char.gender && char.gender !== '人物' && char.gender !== '未识别'
                    ? 'bg-green-500/10 text-green-400'
                    : 'bg-yellow-500/10 text-yellow-400'
                }`}>
                  {char.gender || '未指定'}
                </span>
                {char.importance === 'high' && (
                  <span className="rounded bg-purple-500/10 px-1.5 py-0.5 text-xs text-purple-400">
                    重要
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
