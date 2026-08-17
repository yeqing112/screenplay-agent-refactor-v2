import { describe, expect, it } from 'vitest'
import { buildContentModelContextSummary } from './productWorkspaceContentModels'

describe('buildContentModelContextSummary', () => {
  it('returns readable titles when llm and embedding defaults exist', () => {
    const summary = buildContentModelContextSummary({
      llm: {
        id: 'llm-1',
        name: 'DeepSeek',
        capability: 'llm',
        provider: 'openai-compatible',
        base_url: 'https://api.example.com',
        model_name: 'deepseek-v4-flash',
        default_params: {},
        enabled: true,
        is_default: true,
        key_configured: true,
        builtin: false,
        source: 'user',
        uses_mock: false,
      },
      embedding: {
        id: 'embed-1',
        name: 'Nomic Embed',
        capability: 'embedding',
        provider: 'ollama',
        base_url: 'http://localhost:11434',
        model_name: 'nomic-embed-text',
        default_params: {},
        enabled: true,
        is_default: true,
        key_configured: true,
        builtin: true,
        source: 'env',
        uses_mock: false,
      },
    })

    expect(summary.ready).toBe(true)
    expect(summary.statusLabel).toBe('已接入模型上下文')
    expect(summary.llmTitle).toContain('DeepSeek')
    expect(summary.embeddingProvider).toBe('ollama')
  })

  it('falls back cleanly when defaults are missing', () => {
    const summary = buildContentModelContextSummary({})

    expect(summary.ready).toBe(false)
    expect(summary.statusLabel).toBe('待补模型配置')
    expect(summary.llmTitle).toBe('未配置默认 LLM')
    expect(summary.embeddingTitle).toBe('未配置默认向量模型')
  })
})
