import { useRef, useCallback } from 'react'
import { Room, RoomEvent, Track } from 'livekit-client'

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || ''

function _makeSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SR) return null
  const rec = new SR()
  rec.continuous = true
  rec.interimResults = false
  rec.lang = 'en-US'
  return rec
}

export function useLiveKitVoice({
  onCallReady,
  onTranscript,
  onAgentToken,
  onAgentDone,
  onEscalation,
  onEscalationCancelled,
  onHumanAgentJoined,
  onCallEnded,
  onToolCall,
  onGuardrailBlock,
  onSentiment,
  onKbHit,
  onOtpSent,
  onOtpVerified,
}) {
  const roomRef          = useRef(null)
  const escRoomRef       = useRef(null)
  const callIdRef        = useRef(null)
  const customerSpeechRef = useRef(null)

  const startCall = useCallback(async (initialTopic) => {
    // Play silent audio during the user gesture so Chrome grants sticky
    // activation — this lets element.play() succeed when the agent's audio
    // track arrives seconds later (outside the gesture window).
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const buf = ctx.createBuffer(1, 1, ctx.sampleRate)
      const src = ctx.createBufferSource()
      src.buffer = buf
      src.connect(ctx.destination)
      src.start(0)
      // Leave ctx open — closing it immediately can race with the browser
      // finishing the playback that grants sticky activation.
      setTimeout(() => ctx.close().catch(() => {}), 500)
    } catch {}

    // adaptiveStream: false — adaptive stream pauses subscriptions when audio elements
    // are not visible in the DOM. With it enabled, tracks from participants who join
    // mid-call (e.g. human agent) get their subscription paused because the audio
    // element created by track.attach() isn't in the DOM yet. Disable it so all
    // audio subscriptions stay active regardless of DOM visibility.
    const room = new Room({ adaptiveStream: false, dynacast: false })
    roomRef.current = room

    const resp = await fetch(`${BACKEND}/api/livekit/start-call`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initial_topic: initialTopic || null }),
    })
    if (!resp.ok) throw new Error(`start-call failed: ${resp.status}`)
    const { token, room_name, livekit_url, call_id } = await resp.json()
    callIdRef.current = call_id

    room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      if (!room.canPlaybackAudio) room.startAudio().catch(() => {})
    })

    // Append audio elements to the DOM so the browser's managed media pipeline
    // keeps them alive and playing. Without appendChild(), audio elements created
    // by track.attach() float in memory with no autoplay guarantee in some browsers.
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        const el = track.attach()
        el.style.cssText = 'position:absolute;width:1px;height:1px;opacity:0;pointer-events:none'
        document.body.appendChild(el)
        room.startAudio().catch(() => {})
      }
    })

    // Clean up audio elements when a participant leaves or unpublishes
    room.on(RoomEvent.TrackUnsubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        track.detach().forEach(el => el.remove())
      }
    })

    room.on(RoomEvent.DataReceived, (payload) => {
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload))
        switch (msg.type) {
          case 'call_ready':      onCallReady?.(msg); break
          case 'transcript':      onTranscript?.(msg.speaker, msg.text, msg.is_final); break
          case 'agent_token':     onAgentToken?.(msg.token); break
          case 'agent_done':      onAgentDone?.(msg.full_text); break
          case 'tool_call':       onToolCall?.(msg.tool, msg.status, msg.result); break
          case 'guardrail_block': onGuardrailBlock?.(msg.tool, msg.reason); break
          case 'escalation':           onEscalation?.(msg); break
          case 'escalation_cancelled': onEscalationCancelled?.(msg); break
          case 'human_agent_joined':
            onHumanAgentJoined?.(msg)
            // Deepgram (LiveKit Agents worker) handles customer STT and forwards to agent console.
            // No browser-side STT needed here — it would fight LiveKit for the mic.
            break
          case 'otp_sent':        onOtpSent?.(msg.otp); break
          case 'otp_verified':    onOtpVerified?.(); break
          case 'call_ended':      onCallEnded?.(msg); break
          case 'sentiment':       onSentiment?.(msg.score); break
          case 'kb_hit':          onKbHit?.(msg); break
          case 'agent_transcript':
          case 'agent_message':   onTranscript?.('agent', msg.text, true); break
        }
      } catch {
        // ignore malformed data channel messages
      }
    })

    room.on(RoomEvent.Disconnected, () => onCallEnded?.({}))

    await room.connect(livekit_url, token, { autoSubscribe: true })

    // Transition UI immediately — don't block on mic enabling latency
    onCallReady?.({ call_id })

    // Enable mic after UI is live (non-blocking for UI transition)
    room.localParticipant.setMicrophoneEnabled(true).catch(() => {})

    return { call_id }
  }, [onCallReady, onTranscript, onAgentToken, onAgentDone,
      onEscalation, onCallEnded, onToolCall, onGuardrailBlock,
      onSentiment, onKbHit, onEscalationCancelled, onHumanAgentJoined, onOtpSent])

  const connectToEscalationRoom = useCallback(async (customerToken, livekitUrl) => {
    if (!customerToken || !livekitUrl) return
    if (escRoomRef.current) return  // already connected
    const escRoom = new Room({ adaptiveStream: false, dynacast: false })
    escRoomRef.current = escRoom

    // Unlock audio as early as possible — browsers block autoplay on programmatic
    // actions (escalation fires from a data channel event, not a user gesture).
    // Sticky activation from startCall() should cover desktop Chrome/Firefox.
    escRoom.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      if (!escRoom.canPlaybackAudio) escRoom.startAudio().catch(() => {})
    })

    escRoom.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        const el = track.attach()
        el.style.cssText = 'position:absolute;width:1px;height:1px;opacity:0;pointer-events:none'
        document.body.appendChild(el)
        // Explicit play() + startAudio() for maximum browser compat.
        el.play().catch(() => {})
        escRoom.startAudio().catch(() => {})
      }
    })

    escRoom.on(RoomEvent.TrackUnsubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        track.detach().forEach(el => el.remove())
      }
    })

    // When the human agent joins the esc room, notify the customer UI
    // so it can transition back from TransferScreen → CallScreen.
    escRoom.on(RoomEvent.ParticipantConnected, (participant) => {
      if (participant.identity === 'human-agent') {
        onHumanAgentJoined?.({})
      }
    })

    try {
      await escRoom.connect(livekitUrl, customerToken, { autoSubscribe: true })

      // Edge case: agent joined before customer's esc room finished connecting
      for (const [, p] of escRoom.remoteParticipants) {
        if (p.identity === 'human-agent') {
          onHumanAgentJoined?.({})
          break
        }
      }
      // Pre-unlock the room's audio context right after connect so that when the
      // agent's track arrives, the audio element can auto-play without a gesture.
      escRoom.startAudio().catch(() => {})
      // Two-way audio: customer mic published to esc room so the agent can hear them live.
      // AEC prevents the agent's voice (playing through customer speakers) from echoing back.
      await escRoom.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl:  true,
      })
    } catch (e) {
      console.error('[useLiveKitVoice] escalation room connect failed', e)
      escRoomRef.current = null  // clear so reconnect is possible on retry
    }
  }, [onHumanAgentJoined])

  const endCall = useCallback(async () => {
    const rec = customerSpeechRef.current
    if (rec) {
      customerSpeechRef.current = null
      try { rec.stop() } catch (_) {}
    }
    try {
      await escRoomRef.current?.disconnect()
    } catch {}
    escRoomRef.current = null
    try {
      await roomRef.current?.disconnect()
    } catch {}
    roomRef.current = null
    callIdRef.current = null
  }, [])

  const getCallId = useCallback(() => callIdRef.current, [])

  const setMicEnabled = useCallback(async (enabled) => {
    try {
      await roomRef.current?.localParticipant?.setMicrophoneEnabled(enabled)
    } catch {}
    // Also toggle mic in escalation room if connected
    try {
      await escRoomRef.current?.localParticipant?.setMicrophoneEnabled(enabled)
    } catch {}
  }, [])

  const sendBrowserTranscript = useCallback(async (text) => {
    const room = roomRef.current
    if (!room) return
    const msg = JSON.stringify({ type: 'keypad_input', text, is_final: true })
    try {
      await room.localParticipant.publishData(new TextEncoder().encode(msg), { reliable: true })
    } catch {}
  }, [])

  return { startCall, endCall, setMicEnabled, sendBrowserTranscript, getCallId, connectToEscalationRoom }

}

