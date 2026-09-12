import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { LayoutDashboard, Film } from 'lucide-react'

import ProductWorkspaceShell from './ProductWorkspaceShell'

describe('ProductWorkspaceShell navigation accessibility', () => {
  const baseProps = {
    bookTitle: '测试项目',
    projectStatus: 'draft',
    section: 'dashboard' as const,
    sections: [
      { id: 'dashboard' as const, label: '项目概览', icon: LayoutDashboard, group: '创作' },
      { id: 'storyboard' as const, label: '分镜工作台', icon: Film, group: '生产与检查' },
    ],
    loading: false,
    error: null,
    onSelectSection: vi.fn(),
    getSectionBlockedReason: () => null,
    onRefreshAll: vi.fn(),
    children: <div>内容</div>,
  }

  it('marks the active section as the current page', () => {
    const html = renderToStaticMarkup(<ProductWorkspaceShell {...baseProps} />)

    expect(html).toContain('aria-current="page"')
    expect(html.match(/aria-current="page"/g)).toHaveLength(1)
  })

  it('exposes a visible keyboard focus treatment for every navigation button', () => {
    const html = renderToStaticMarkup(<ProductWorkspaceShell {...baseProps} />)

    expect(html).toContain('focus-visible:ring-2')
    expect(html).toContain('focus-visible:ring-violet-400')
    expect(html.match(/focus-visible:ring-2/g)).toHaveLength(2)
  })
})
