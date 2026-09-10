import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SmartDirectorDrawer from './SmartDirectorDrawer'
import type { DirectorContext } from '../services/agent'

describe('SmartDirectorDrawer', () => {
  const context: DirectorContext = {
    book_id: 75,
    book_title: '便利店收银台',
    section: '镜头工作台',
    shot_id: 3,
  }

  it('renders the floating trigger button even when closed', () => {
    const html = renderToStaticMarkup(<SmartDirectorDrawer context={context} />)
    expect(html).toContain('智能导演台')
    expect(html).toContain('打开智能导演台')
  })

  it('handles a null context without crashing', () => {
    const html = renderToStaticMarkup(<SmartDirectorDrawer context={null} />)
    expect(html).toContain('智能导演台')
  })

  it('uses semantic landmarks and accessible labels', () => {
    const html = renderToStaticMarkup(<SmartDirectorDrawer context={context} />)
    expect(html).toContain('aria-label="打开智能导演台"')
  })
})
