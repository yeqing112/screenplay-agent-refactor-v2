import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { getEpisodeStorageKey, readStoredEpisode, resolveEpisodeSelection } from './DirectorMode'

describe('DirectorMode episode selection', () => {
  const storage = new Map<string, string>()

  beforeEach(() => {
    storage.clear()
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, String(value))
        },
        removeItem: (key: string) => {
          storage.delete(key)
        },
        clear: () => {
          storage.clear()
        },
      },
    })
  })

  afterEach(() => {
    storage.clear()
  })

  it('reads the stored episode for the current project', () => {
    localStorage.setItem(getEpisodeStorageKey(12), '2')

    expect(readStoredEpisode(12)).toBe(2)
    expect(readStoredEpisode(13)).toBeNull()
  })

  it('prefers the stored episode when it is available in the current project', () => {
    localStorage.setItem(getEpisodeStorageKey(7), '2')

    expect(resolveEpisodeSelection(7, [1, 2], 1)).toBe(2)
  })

  it('falls back to the current episode when the stored episode belongs to another project state', () => {
    localStorage.setItem(getEpisodeStorageKey(7), '2')

    expect(resolveEpisodeSelection(7, [1], 1)).toBe(1)
  })

  it('falls back to the first available episode when neither stored nor current episodes are valid', () => {
    localStorage.setItem(getEpisodeStorageKey(7), '9')

    expect(resolveEpisodeSelection(7, [3, 4], 2)).toBe(3)
  })

  it('falls back to episode 1 when no episodes are available', () => {
    expect(resolveEpisodeSelection(undefined, [], 5)).toBe(1)
  })
})
