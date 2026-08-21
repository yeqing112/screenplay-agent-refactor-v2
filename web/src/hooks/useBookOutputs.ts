import { useCallback, useEffect, useState } from 'react'
import { createEmptyOutputsData, normalizeBookOutputs, type OutputsData } from '../domain/bookOutputs'

interface UseBookOutputsResult {
  data: OutputsData | null
  loading: boolean
  error: string | null
  refresh: () => void
}

export function useBookOutputs(bookId?: number): UseBookOutputsResult {
  const [data, setData] = useState<OutputsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)

    if (!bookId || bookId <= 0) {
      setData(createEmptyOutputsData())
      setLoading(false)
      return
    }

    try {
      const response = await fetch(`/api/pipeline/book/${bookId}/outputs`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const payload = await response.json()
      setData(normalizeBookOutputs(payload))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [bookId])

  useEffect(() => {
    load()
  }, [load])

  return { data, loading, error, refresh: load }
}
