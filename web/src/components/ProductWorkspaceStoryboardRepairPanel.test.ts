import { describe, expect, it } from 'vitest'

import { splitStoryboardRepairActions } from './ProductWorkspaceStoryboardRepairPanel'

describe('splitStoryboardRepairActions', () => {
  it('keeps a single highest-priority action visible and moves the rest behind an explicit expansion', () => {
    const actions = [
      { key: 'first', label: '先补资产' },
      { key: 'second', label: '再重编提示词' },
      { key: 'third', label: '最后生成首帧' },
    ]

    expect(splitStoryboardRepairActions(actions)).toEqual({
      primary: actions[0],
      remaining: [actions[1], actions[2]],
    })
  })
})
