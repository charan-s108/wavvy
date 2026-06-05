import { useState, useEffect, useCallback } from 'react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'

export function useSupervisorPolling(intervalMs = 5000) {
  const [liveCalls, setLiveCalls] = useState([])
  const [kpis, setKpis] = useState(null)
  const [callHistory, setCallHistory] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const [liveResp, kpiResp, histResp] = await Promise.all([
        fetch(`${API}/api/dashboard/live-calls`),
        fetch(`${API}/api/dashboard/kpis`),
        fetch(`${API}/api/calls`),
      ])

      if (liveResp.ok) setLiveCalls(await liveResp.json())
      if (kpiResp.ok) setKpis(await kpiResp.json())
      if (histResp.ok) setCallHistory(await histResp.json())
    } catch {
      // silently handle — will retry
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, intervalMs)
    return () => clearInterval(id)
  }, [fetchData, intervalMs])

  return { liveCalls, kpis, callHistory, loading, refetch: fetchData }
}
