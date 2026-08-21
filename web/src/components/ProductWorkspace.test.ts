import { describe, expect, it } from 'vitest'

import { buildEpisodeSequence } from './ProductWorkspace'

describe('ProductWorkspace', () => {
  it('builds storyboard episode payloads from the configured episode count', () => {
    expect(buildEpisodeSequence(3)).toEqual([1, 2, 3])
    expect(buildEpisodeSequence(0)).toEqual([1])
  })
})
