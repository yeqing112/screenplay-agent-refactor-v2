import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  sectionLabel: string
}

interface State {
  error: Error | null
}

export default class WorkspaceSectionErrorBoundary extends Component<Props, State> {
  state: State = {
    error: null,
  }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error(`Workspace section render failed: ${this.props.sectionLabel}`, error)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-100">
          <div className="font-medium">模块渲染失败：{this.props.sectionLabel}</div>
          <div className="mt-2 break-words text-rose-200">
            {this.state.error.message || '未知错误'}
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
