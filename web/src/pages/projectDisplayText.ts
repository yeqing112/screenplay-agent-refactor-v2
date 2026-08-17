const INVALID_PROJECT_TITLE_SIGNALS = [
  '\u65e0\u6cd5\u4ece\u7ed9\u5b9a\u6587\u672c\u4e2d\u63d0\u53d6\u6807\u9898',
  '\u8bf7\u63d0\u4f9b\u5305\u542b\u4e66\u540d',
  '\u8bf7\u63d0\u4f9b\u5305\u542b\u4e66\u7c7b\u6545\u4e8b\u6807\u9898',
  '\u8bf7\u63d0\u4f9b\u5305\u542b\u4e66\u7c4d/\u6545\u4e8b\u6807\u9898',
  '\u672a\u5305\u542b\u4e66\u7c7b\u6216\u6545\u4e8b\u6807\u9898\u4fe1\u606f',
  '\u6807\u9898\u4fe1\u606f',
]

const MOJIBAKE_PATTERNS = ['\u95bf', '\u9474', '\u59d8', '\u8e47', '\u9e1e', '\u94a9', '\u9435', '\u5a34']
const LEGACY_MOJIBAKE_MARKERS = ['锟斤拷', '閿熸枻鎷', '鏈懡鍚', '璇锋彁渚', '鏃犳硶浠']

export function isLikelyCorruptedProjectTitle(value: unknown) {
  if (typeof value !== 'string') return false
  const text = value.trim()
  if (!text) return false

  if (text.includes('????') || text.includes('\u95bf?') || LEGACY_MOJIBAKE_MARKERS.some((token) => text.includes(token))) {
    return true
  }

  const compact = text.replace(/\s+/g, '')
  const questionMarks = compact.match(/\?/g)?.length ?? 0
  if (questionMarks >= 2 && questionMarks / compact.length >= 0.2) {
    return true
  }

  if (!/[\u4e00-\u9fff]/.test(compact) && MOJIBAKE_PATTERNS.some((token) => compact.includes(token))) {
    return true
  }

  return INVALID_PROJECT_TITLE_SIGNALS.some((signal) => text.includes(signal))
}

export function resolveProjectDisplayTitle(title: unknown, bookId: number) {
  const normalized = typeof title === 'string' ? title.trim() : ''
  if (!normalized || isLikelyCorruptedProjectTitle(normalized)) {
    return `\u672a\u547d\u540d\u9879\u76ee ${bookId}`
  }
  return normalized
}
