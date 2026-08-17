export interface NodeSpec {
  name: string
  label: string
  category: string
  description: string
  inputs: NodeInput[]
  outputs: NodeOutput[]
  agent_class?: string
  default_prompt?: string
}

export interface NodeInput {
  name: string
  label: string
  type: string
  required: boolean
  default?: any
  options?: string[]
}

export interface NodeOutput {
  name: string
  label: string
  type: string
}

export interface CanvasNodeData {
  spec: NodeSpec
  inputs: Record<string, any>
  config: Record<string, any>
  runId?: string
  runStatus?: 'idle' | 'running' | 'done' | 'error'
}

export interface RunResult {
  status: string
  result?: any
  logs?: string[]
}
