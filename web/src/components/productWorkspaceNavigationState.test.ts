import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  getProductWorkspaceNavigationStateStorageKey,
  readProductWorkspaceNavigationState,
  writeProductWorkspaceNavigationState,
} from './productWorkspaceNavigationState'

function createStorage() {
  const store = new Map<string, string>()
  return {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value)
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key)
    }),
  }
}

describe('productWorkspaceNavigationState', () => {
  beforeEach(() => {
    const storage = createStorage()
    Object.defineProperty(globalThis, 'window', {
      value: { localStorage: storage },
      configurable: true,
    })
  })

  it('persists only canvas recovery navigation state', () => {
    writeProductWorkspaceNavigationState(14, {
      section: 'canvas',
      canvasNavigationTarget: {
        episode: 1,
        shotId: '3',
        taskId: 'task-1',
        recoveryKind: 'frame',
      },
    })

    expect(readProductWorkspaceNavigationState(14)).toEqual({
      section: 'canvas',
      canvasNavigationTarget: {
        episode: 1,
        shotId: '3',
        assetId: null,
        assetLabel: null,
        taskId: 'task-1',
        recoveryKind: 'frame',
        recoveryIntent: null,
      },
    })
  })

  it('drops invalid or non-canvas state on read', () => {
    window.localStorage.setItem(
      getProductWorkspaceNavigationStateStorageKey(14),
      JSON.stringify({
        section: 'tasks',
        canvasNavigationTarget: { episode: 1, shotId: '3' },
      }),
    )

    expect(readProductWorkspaceNavigationState(14)).toBeNull()
  })

  it('clears storage when state becomes empty', () => {
    writeProductWorkspaceNavigationState(14, {
      section: 'canvas',
      canvasNavigationTarget: {
        episode: 1,
        shotId: '3',
      },
    })

    writeProductWorkspaceNavigationState(14, null)

    expect(window.localStorage.getItem(getProductWorkspaceNavigationStateStorageKey(14))).toBeNull()
  })
})
