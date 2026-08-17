export interface AdaptationOption {
  id: string
  name: string
  audience: string
  hook: string
  strength: string
  rhythm: string
  keep: string
  enhance: string
  risk: string
}

interface BuildAdaptationOptionsInput {
  title: string
  chapterCount: number
  wordCount: number
  scriptExcerpt?: string
}

function inferStrength(wordCount: number) {
  if (wordCount >= 120000) return '\u4e2d\u6539'
  if (wordCount >= 30000) return '\u8f7b\u4e2d\u6539'
  return '\u8f7b\u6539'
}

function inferSourceSignal(title: string, scriptExcerpt?: string) {
  const seed = normalizeSourceSignal(scriptExcerpt)
  if (seed) {
    return seed
  }
  return title.trim() || '\u539f\u4f5c\u6838\u5fc3\u51b2\u7a81'
}

export function buildAdaptationOptions(input: BuildAdaptationOptionsInput): AdaptationOption[] {
  const cleanTitle = input.title.trim() || '\u5f53\u524d\u9879\u76ee'
  const sourceSignal = inferSourceSignal(cleanTitle, input.scriptExcerpt)
  const chapterScale = input.chapterCount > 0 ? `${input.chapterCount} \u7ae0\u7d20\u6750` : '\u5f85\u6574\u7406\u7d20\u6750'
  const strength = inferStrength(input.wordCount)

  return [
    {
      id: 'emotion-suspense',
      name: '\u7ad6\u5c4f\u60c5\u7eea\u60ac\u7591\u77ed\u5267',
      audience: '25-45 \u5c81\u5973\u6027\u7528\u6237',
      hook: `\u56f4\u7ed5\u201c${cleanTitle}\u201d\u5efa\u7acb\u5371\u9669\u5173\u7cfb\u4e0e\u60c5\u7eea\u8bd5\u63a2\uff0c\u9996\u96c6\u5373\u629b\u51fa\u60ac\u5ff5\u94a9\u5b50\u3002`,
      strength,
      rhythm: '\u5f3a\u94a9\u5b50\u3001\u77ed\u56de\u5408\u3001\u9ad8\u505c\u987f\u3001\u7ed3\u5c3e\u53cd\u95ee',
      keep: `\u4fdd\u7559 ${chapterScale} \u4e2d\u6700\u5f3a\u7684\u4eba\u7269\u5173\u7cfb\u7ebf\u4e0e\u538b\u8feb\u611f\u6765\u6e90\uff1a${sourceSignal}`,
      enhance: '\u52a0\u5f3a\u7ed3\u5c3e\u60ac\u5ff5\u3001\u4eba\u7269\u8bef\u5224\u3001\u5177\u4f53\u52a8\u4f5c\u5207\u70b9\u4e0e\u955c\u5934\u5316\u60c5\u7eea\u6ce2\u5cf0\u3002',
      risk: '\u8981\u907f\u514d\u53ea\u5269\u6c1b\u56f4\uff0c\u6ca1\u6709\u660e\u786e\u51b2\u7a81\u63a8\u8fdb\u3002',
    },
    {
      id: 'urban-relationship',
      name: '\u90fd\u5e02\u5173\u7cfb\u6d41\u8fde\u7eed\u77ed\u5267',
      audience: '18-30 \u5c81\u5973\u6027\u7528\u6237',
      hook: `\u628a\u201c${cleanTitle}\u201d\u6539\u9020\u6210\u53ef\u8fde\u7eed\u8ffd\u66f4\u7684\u4eba\u7269\u5173\u7cfb\u620f\uff0c\u7a81\u51fa\u9760\u8fd1\u4e0e\u9632\u5907\u5e76\u5b58\u3002`,
      strength: strength === '\u4e2d\u6539' ? '\u8f7b\u4e2d\u6539' : '\u8f7b\u6539',
      rhythm: '\u5173\u7cfb\u9012\u8fdb\u3001\u4fe1\u606f\u5ef6\u8fdf\u3001\u5bf9\u8bdd\u62c9\u626f\u3001\u6c14\u6c1b\u4f18\u5148',
      keep: `\u4fdd\u7559\u539f\u4f5c\u4eba\u7269\u89c6\u89d2\u4e0e\u60c5\u7eea\u4f59\u5473\uff0c\u6838\u5fc3\u7d20\u6750\u951a\u70b9\u4e3a\uff1a${sourceSignal}`,
      enhance: '\u5f3a\u5316\u5bf9\u8bdd\u5f20\u529b\u3001\u5173\u7cfb\u9519\u4f4d\u3001\u89c6\u89c9\u7b26\u53f7\u548c\u4eba\u7269\u610f\u56fe\u5916\u663e\u3002',
      risk: '\u8981\u63a7\u5236\u8282\u594f\uff0c\u907f\u514d\u8fde\u7eed\u5267\u5316\u540e\u5931\u53bb\u77ed\u5267\u94a9\u5b50\u6548\u7387\u3002',
    },
    {
      id: 'twist-driven',
      name: '\u5f3a\u53cd\u8f6c\u5267\u60c5\u5411\u77ed\u5267',
      audience: '\u5927\u4f17\u77ed\u5267\u7528\u6237',
      hook: `\u7528\u201c${cleanTitle}\u201d\u7684\u4eba\u7269\u8bbe\u5b9a\u505a\u9ad8\u5bc6\u5ea6\u53cd\u8f6c\uff0c\u6bcf\u96c6\u90fd\u7ed9\u51fa\u660e\u786e\u4e8b\u4ef6\u63a8\u8fdb\u3002`,
      strength: '\u4e2d\u9ad8\u6539',
      rhythm: '\u5feb\u8282\u594f\u3001\u5f3a\u8f6c\u573a\u3001\u5f3a\u4fe1\u606f\u5dee\u3001\u7ed3\u679c\u5148\u884c',
      keep: `\u4fdd\u7559\u539f\u4f5c\u6838\u5fc3\u8bbe\u5b9a\u548c\u6700\u6709\u8fa8\u8bc6\u5ea6\u7684\u4eba\u7269\u5173\u7cfb\uff0c\u57fa\u7840\u7d20\u6750\u6765\u81ea\uff1a${sourceSignal}`,
      enhance: '\u52a0\u5bc6\u51b2\u7a81\u3001\u538b\u7f29\u94fa\u57ab\u3001\u524d\u7f6e\u7206\u70b9\u3001\u63d0\u9ad8\u6bcf\u96c6\u7ed3\u5c3e\u7ffb\u9762\u6982\u7387\u3002',
      risk: '\u8981\u9632\u6b62\u53cd\u8f6c\u5806\u53e0\u5bfc\u81f4\u4eba\u7269\u52a8\u673a\u5931\u771f\u3002',
    },
  ]
}

export function getSelectedAdaptation(
  options: AdaptationOption[],
  selectedId: string | null,
): AdaptationOption | null {
  if (!selectedId) {
    return null
  }
  return options.find((option) => option.id === selectedId) ?? null
}

function normalizeSourceSignal(scriptExcerpt?: string) {
  const plain = String(scriptExcerpt ?? '')
    .replace(/[#>*_`~\[\]\-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  if (!plain) {
    return ''
  }

  return plain.slice(0, 36)
}
