import { useState, useCallback, useEffect } from 'react'
import { delay } from './mockData'
import { MOCK_OUTPUTS_DATA, type OutputsData } from './sceneComposerData'

interface UseMockOutputsReturn {
  data: OutputsData | null
  loading: boolean
  error: string | null
  refresh: () => void
}

export function useMockOutputs(): UseMockOutputsReturn {
  const [data, setData] = useState<OutputsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      await delay(400)
      // Simulate: first load takes 400ms, then it's cached
      setData(MOCK_OUTPUTS_DATA)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return { data, loading, error, refresh: load }
}
