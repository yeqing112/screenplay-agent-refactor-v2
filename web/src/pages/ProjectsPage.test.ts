import { describe, expect, it } from 'vitest'
import { buildProjectCardBooks, resolveProjectStatusLabel } from './ProjectsPage'

describe('buildProjectCardBooks', () => {
  it('keeps duplicate project titles instead of collapsing them', () => {
    const items = buildProjectCardBooks([
      {
        id: 14,
        title: '三个和尚',
        chapters: 1,
        words: 32,
        status: 'scripted',
        scripts: 1,
        storyboard_shots: 24,
        created_at: '2026-06-27T02:23:56.491510',
      },
      {
        id: 17,
        title: '三个和尚',
        chapters: 1,
        words: 136,
        status: 'outlined',
        scripts: 19,
        storyboard_shots: 0,
        created_at: '2026-07-12T06:12:22.676985',
      },
    ])

    expect(items).toHaveLength(2)
    expect(items.map((item) => item.displayTitle)).toEqual(['三个和尚 · #14', '三个和尚 · #17'])
    expect(items.map((item) => item.duplicateTitleCount)).toEqual([2, 2])
  })

  it('keeps single-title projects readable without an id suffix', () => {
    const [item] = buildProjectCardBooks([
      {
        id: 5,
        title: '神农架历险记',
        chapters: 40,
        words: 26922,
        status: 'scripted',
        scripts: 8,
        storyboard_shots: 20,
        created_at: '2026-06-23T13:16:31.410233',
      },
    ])

    expect(item.displayTitle).toBe('神农架历险记')
    expect(item.duplicateTitleCount).toBe(1)
  })

  it('maps legacy bible statuses to clean Chinese labels', () => {
    expect(resolveProjectStatusLabel('bibled')).toBe('小说圣经完成')
    expect(resolveProjectStatusLabel('bibeled')).toBe('小说圣经完成')
  })
})
