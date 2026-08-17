import { useState, useCallback, useRef, useEffect } from 'react'
import { delay } from './mockData'

export type TaskState = 'idle' | 'running' | 'done' | 'error'

export interface UseTaskRunnerReturn {
  state: TaskState
  progress: number
  step: string
  error: string | null
  run: (steps: { label: string; duration: number }[]) => void
  reset: () => void
}

/**
 * Mock task runner with simulated progress.
 * Demonstrates the unified poll pattern.
 */
export function useTaskRunner(): UseTaskRunnerReturn {
  const [state, setState] = useState<TaskState>('idle')
  const [progress, setProgress] = useState(0)
  const [step, setStep] = useState('')
  const [error, setError] = useState<string | null>(null)
  const stoppedRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cleanup = useCallback(() => {
    stoppedRef.current = true
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  useEffect(() => cleanup, [cleanup])

  const run = useCallback(async (steps: { label: string; duration: number }[]) => {
    cleanup()
    stoppedRef.current = false
    setState('running')
    setProgress(0)
    setError(null)

    let totalProgress = 0
    for (let i = 0; i < steps.length; i++) {
      if (stoppedRef.current) return
      const s = steps[i]
      setStep(s.label)
      const startProgress = totalProgress
      const endProgress = ((i + 1) / steps.length) * 100

      // Simulate step progress in chunks
      const chunkMs = 300
      const chunks = Math.ceil(s.duration / chunkMs)
      for (let c = 0; c < chunks; c++) {
        if (stoppedRef.current) return
        await delay(chunkMs)
        const fraction = (c + 1) / chunks
        setProgress(Math.round(startProgress + (endProgress - startProgress) * fraction))
      }
      totalProgress = endProgress
    }

    if (!stoppedRef.current) {
      setState('done')
      setProgress(100)
      setStep('完成')
    }
  }, [cleanup])

  const reset = useCallback(() => {
    cleanup()
    setState('idle')
    setProgress(0)
    setStep('')
    setError(null)
  }, [cleanup])

  return { state, progress, step, error, run, reset }
}
