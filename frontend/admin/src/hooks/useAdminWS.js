/**
 * useAdminWS — replaces useAdminPolling.
 *
 * Connects to /ws/admin and reacts to push events:
 *   init         → seeds liveCalls; triggers one-shot HTTP fetch for kpis + history
 *   call_started → prepends to liveCalls (no poll needed)
 *   call_ended   → removes from liveCalls; refetches kpis + history once
 *   eval_ready   → prepends to evals
 *
 * No setInterval anywhere. Data only moves when the server says something changed.
 */
import { useState, useEffect, useRef, useCallback } from 'react'

const API    = import.meta.env.VITE_BACKEND_HTTP_URL  || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_BACKEND_WS_URL
  || API.replace(/^http/, 'ws')

async function fetchJSON(path) {
  const r = await fetch(`${API}${path}`)
  if (!r.ok) throw new Error(r.statusText)
  return r.json()
}

export function useAdminWS() {
  const [liveCalls,    setLiveCalls]    = useState([])
  const [kpis,         setKpis]         = useState(null)
  const [callHistory,  setCallHistory]  = useState([])
  const [evals,        setEvals]        = useState([])
  const [connected,    setConnected]    = useState(false)

  const wsRef      = useRef(null)
  const retryTimer = useRef(null)

  // Fetch KPIs + call history in one shot (called on connect + after call_ended)
  const refreshSnapshot = useCallback(async () => {
    try {
      const [kpiData, histData] = await Promise.all([
        fetchJSON('/api/dashboard/kpis'),
        fetchJSON('/api/calls'),
      ])
      setKpis(kpiData)
      setCallHistory(histData)
    } catch { /* silently retry on next event */ }
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(`${WS_URL}/ws/admin`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      if (retryTimer.current) {
        clearTimeout(retryTimer.current)
        retryTimer.current = null
      }
    }

    ws.onmessage = (evt) => {
      let msg
      try { msg = JSON.parse(evt.data) } catch { return }

      if (msg.type === 'init') {
        setLiveCalls(msg.live_calls || [])
        refreshSnapshot()
      } else if (msg.type === 'call_started') {
        setLiveCalls(prev => {
          if (prev.some(c => c.call_id === msg.call_id)) return prev
          return [{ call_id: msg.call_id, started_at: msg.started_at }, ...prev]
        })
      } else if (msg.type === 'call_ended') {
        setLiveCalls(prev => prev.filter(c => c.call_id !== msg.call_id))
        refreshSnapshot()
      } else if (msg.type === 'eval_ready') {
        setEvals(prev => {
          const without = prev.filter(e => e.call_id !== msg.call_id)
          return [{ call_id: msg.call_id, ...msg.scores }, ...without]
        })
      } else if (msg.type === 'feedback_submitted') {
        setEvals(prev => prev.map(e =>
          e.call_id === msg.call_id
            ? { ...e, customer_rating: msg.rating, customer_feedback: msg.comment }
            : e
        ))
      }
    }

    ws.onclose = () => {
      setConnected(false)
      // Exponential back-off reconnect: 2s → 4s → 8s (cap 30s)
      const delay = Math.min(30000, 2000 * (1 + Math.random()))
      retryTimer.current = setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [refreshSnapshot])

  useEffect(() => {
    connect()
    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return {
    liveCalls,
    kpis,
    callHistory,
    evals,
    connected,
    loading: !connected && kpis === null,
    refetchEvals: useCallback(async () => {
      try {
        const data = await fetchJSON('/api/eval/recent/all?limit=30')
        setEvals(data)
      } catch { /* ignore */ }
    }, []),
  }
}
