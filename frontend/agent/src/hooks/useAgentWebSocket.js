import { useRef, useCallback, useEffect } from 'react'

const _HTTP = import.meta.env.VITE_BACKEND_HTTP_URL || ''
const WS_BASE = import.meta.env.VITE_BACKEND_WS_URL ||
  (_HTTP ? _HTTP.replace(/^http/, 'ws') : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`)
const BACKOFF  = [1000, 2000, 4000, 8000, 16000]

export function useAgentWebSocket({
  onIncomingCall,
  onTranscript,
  onCompanionUpdate,
  onAcwReady,
  onCallClosed,
  onAgentReady,
  onStatusUpdated,
  onAuthError,
  onActionResult,
  onActivityEvent,
  onCaseInvestigation,
  onSentimentUpdate,
}) {
  const wsRef     = useRef(null)
  const retryRef  = useRef(0)
  const mountedRef = useRef(true)

  const callbacks = useRef({
    onIncomingCall, onTranscript, onCompanionUpdate, onAcwReady, onCallClosed,
    onAgentReady, onStatusUpdated, onAuthError, onActionResult, onActivityEvent,
    onCaseInvestigation, onSentimentUpdate,
  })
  useEffect(() => {
    callbacks.current = {
      onIncomingCall, onTranscript, onCompanionUpdate, onAcwReady, onCallClosed,
      onAgentReady, onStatusUpdated, onAuthError, onActionResult, onActivityEvent,
      onCaseInvestigation, onSentimentUpdate,
    }
  })

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    const token = localStorage.getItem('wavvy_agent_token') || ''
    if (!token) return   // not logged in — don't attempt connection
    const url   = `${WS_BASE}/ws/agent?token=${encodeURIComponent(token)}`
    const ws    = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      retryRef.current = 0
      ws.send(JSON.stringify({ type: 'agent_ready' }))
    }

    ws.onmessage = (event) => {
      let msg
      try { msg = JSON.parse(event.data) } catch { return }

      const cb = callbacks.current
      switch (msg.type) {
        case 'agent_ready_ack':
          cb.onAgentReady?.({ name: msg.agent_name, email: msg.agent_email, status: msg.status })
          break
        case 'status_updated':
          cb.onStatusUpdated?.(msg.status)
          break
        case 'incoming_call':
          cb.onIncomingCall?.(msg)
          break
        case 'transcript':
          cb.onTranscript?.(msg.speaker, msg.text, msg.is_final)
          break
        case 'companion_update':
          cb.onCompanionUpdate?.(msg)
          break
        case 'acw_ready':
          cb.onAcwReady?.(msg)
          break
        case 'call_closed':
          cb.onCallClosed?.(msg.call_id)
          break
        case 'action_result':
          cb.onActionResult?.(msg)
          break
        case 'activity_event':
          cb.onActivityEvent?.(msg)
          break
        case 'case_investigation':
          cb.onCaseInvestigation?.(msg)
          break
        case 'sentiment_update':
          cb.onSentimentUpdate?.(msg)
          break
        case 'otp_sent':
          // Voice AI sent an OTP — forward as an activity event so it surfaces in the timeline
          cb.onActivityEvent?.({
            type: 'activity_event',
            kind: 'otp_sent_by_ai',
            action: 'send_otp',
            message: `Fin AI sent OTP: ${msg.otp} — customer will read this back.`,
          })
          break
        case 'auth_error':
          // Server says token is invalid — clear and show login immediately
          localStorage.removeItem('wavvy_agent_token')
          localStorage.removeItem('wavvy_agent_info')
          ws.close()
          cb.onAuthError?.()
          break
        default:
          break
      }
    }

    ws.onclose = (e) => {
      if (!mountedRef.current) return
      // 4401 = auth failure — clear storage and signal the app to show login
      // Do NOT reload — the auth_error message handler already called onAuthError,
      // and a reload would restart this loop immediately.
      if (e.code === 4401) {
        localStorage.removeItem('wavvy_agent_token')
        localStorage.removeItem('wavvy_agent_info')
        callbacks.current.onAuthError?.()
        return
      }
      const delay = BACKOFF[Math.min(retryRef.current, BACKOFF.length - 1)]
      retryRef.current++
      setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      wsRef.current?.close()
    }
  }, [connect])

  const sendTranscriptLine = useCallback((text, callId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'transcript_line', text, call_id: callId }))
    }
  }, [])

  const sendEndCall = useCallback((callId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_call', call_id: callId }))
    }
  }, [])

  const sendAcwSubmit = useCallback((acw) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'acw_submit', acw }))
    }
  }, [])

  const sendSetStatus = useCallback((status) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'set_status', status }))
    }
  }, [])

  const sendDeclineCall = useCallback((callId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'decline_call', call_id: callId }))
    }
  }, [])

  const sendActionApproved = useCallback((action, payload, executionId, callId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'action_approved',
        action,
        payload,
        execution_id: executionId,
        call_id: callId,
      }))
    }
  }, [])

  const sendActionRejected = useCallback((action, callId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'action_rejected', action, call_id: callId }))
    }
  }, [])

  return {
    sendTranscriptLine, sendEndCall, sendAcwSubmit, sendSetStatus,
    sendDeclineCall, sendActionApproved, sendActionRejected,
  }
}
