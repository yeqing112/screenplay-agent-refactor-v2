import { describe, expect, it } from 'vitest'
import { isLikelyCorruptedProjectTitle, resolveProjectDisplayTitle } from './projectDisplayText'

describe('projectDisplayText', () => {
  it('falls back when project title is empty or corrupted', () => {
    expect(resolveProjectDisplayTitle('', 12)).toBe('未命名项目 12')
    expect(resolveProjectDisplayTitle('????????-????', 34)).toBe('未命名项目 34')
    expect(resolveProjectDisplayTitle('锟斤拷锟斤拷标题', 56)).toBe('未命名项目 56')
  })

  it('keeps readable titles intact', () => {
    expect(resolveProjectDisplayTitle('雨夜借宿', 7)).toBe('雨夜借宿')
    expect(resolveProjectDisplayTitle('temple-guest-acceptance', 9)).toBe('temple-guest-acceptance')
  })

  it('detects known extraction failure strings', () => {
    expect(isLikelyCorruptedProjectTitle('无法从给定文本中提取标题，请提供包含书名的内容')).toBe(true)
    expect(isLikelyCorruptedProjectTitle('请提供包含书籍/故事标题的文本。')).toBe(true)
    expect(isLikelyCorruptedProjectTitle('寺门归客八')).toBe(false)
  })
})
