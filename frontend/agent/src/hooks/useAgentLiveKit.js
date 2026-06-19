import { useState, useCallback, useRef } from 'react'
import { Room, RoomEvent } from 'livekit-client'

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || ''

export function useAgentLiveKit() {
  const [connected, setConnected]   = useState(false)
  const [micEnabled, setMicEnabled] = useState(true)
  const [joining, setJoining]       = useState(false)
  const roomRef          = useRef(null)
  const recognitionRef   = useRef(null)
  const transcriptCbRef  = useRef(null)  // stable ref so toggleMic can restart recognition

  const _startSpeechRecognition = useCallback((onTranscript) => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return  // Firefox/Safari — no Web Speech API, chat input is the fallback

    transcriptCbRef.current = onTranscript

    const _launch = () => {
      if (recognitionRef.current) return  // already running
      const rec = new SR()
      rec.continuous    = true
      rec.interimResults = false
      rec.lang          = 'en-US'

      rec.onresult = (e) => {
        const text = e.results[e.results.length - 1][0].transcript.trim()
        if (text && transcriptCbRef.current) transcriptCbRef.current(text)
      }

      // Browser auto-stops after silence — restart immediately
      rec.onend = () => {
        if (recognitionRef.current === rec) {
          recognitionRef.current = null
          if (transcriptCbRef.current === onTranscript) {
            setTimeout(_launch, 200)
          }
        }
      }

      // Restart on recoverable errors; give up on permission/hardware errors
      rec.onerror = (e) => {
        recognitionRef.current = null
        if (e.error === 'not-allowed' || e.error === 'audio-capture') return
        if (transcriptCbRef.current === onTranscript) {
          setTimeout(_launch, 1000)
        }
      }

      try { rec.start() } catch (_) { return }
      recognitionRef.current = rec
    }

    _launch()
  }, [])

  const _stopSpeechRecognition = useCallback(() => {
    transcriptCbRef.current = null  // prevent restart from onend/onerror
    const rec = recognitionRef.current
    recognitionRef.current = null
    if (rec) try { rec.stop() } catch (_) {}
  }, [])

  const joinCall = useCallback(async (callId, sendTranscriptLine, onCustomerTranscript, directToken, directLivekitUrl) => {
    if (joining || connected) return
    setJoining(true)
    try {
      let token, livekit_url
      if (directToken && directLivekitUrl) {
        token = directToken
        livekit_url = directLivekitUrl
      } else {
        const resp = await fetch(`${BACKEND}/api/livekit/agent-join`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ call_id: callId }),
        })
        if (!resp.ok) throw new Error(`agent-join failed: ${resp.status}`)
        ;({ token, livekit_url } = await resp.json())
      }

      // adaptiveStream: false — prevents LiveKit from pausing audio subscriptions
      // for tracks whose elements are not visible in the DOM
      const room = new Room({ adaptiveStream: false, dynacast: false })
      room.on(RoomEvent.Disconnected, () => {
        setConnected(false)
        roomRef.current = null
        _stopSpeechRecognition()
      })

      room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        if (!room.canPlaybackAudio) room.startAudio().catch(() => {})
      })

      // Play audio from all remote participants (customer mic).
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === 'audio') {
          const el = track.attach()
          el.style.cssText = 'position:absolute;width:1px;height:1px;opacity:0;pointer-events:none'
          document.body.appendChild(el)
          el.play().catch(() => {})
          room.startAudio().catch(() => {})
        }
      })
      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === 'audio') {
          track.detach().forEach(el => el.remove())
        }
      })

      // Receive customer speech in two forms:
      // 1. {type:"transcript", speaker:"customer"} — Deepgram STT from backend (primary)
      // 2. {type:"customer_transcript"} — browser STT from landing page (fallback)
      if (onCustomerTranscript) {
        room.on(RoomEvent.DataReceived, (payload) => {
          try {
            const msg = JSON.parse(new TextDecoder().decode(payload))
            if (msg.type === 'transcript' && msg.speaker === 'customer' && msg.text && msg.is_final) {
              onCustomerTranscript(msg.text)
            } else if (msg.type === 'customer_transcript' && msg.text) {
              onCustomerTranscript(msg.text)
            }
          } catch {}
        })
      }

      await room.connect(livekit_url, token, { autoSubscribe: true })
      await room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl:  true,
      })
      roomRef.current = room
      setConnected(true)
      setMicEnabled(true)

      // Start transcribing the agent's mic so their speech appears in the transcript feed
      if (sendTranscriptLine) {
        _startSpeechRecognition(sendTranscriptLine)
      }
    } finally {
      setJoining(false)
    }
  }, [joining, connected, _startSpeechRecognition, _stopSpeechRecognition])

  const toggleMic = useCallback(async () => {
    const room = roomRef.current
    if (!room) return
    const next = !micEnabled
    await room.localParticipant.setMicrophoneEnabled(next)
    setMicEnabled(next)
    if (!next) {
      _stopSpeechRecognition()
    } else {
      // Re-enable: restart recognition with the same callback if one was active
      const cb = transcriptCbRef.current
      if (cb) _startSpeechRecognition(cb)
    }
  }, [micEnabled, _stopSpeechRecognition, _startSpeechRecognition])

  const leaveCall = useCallback(async () => {
    _stopSpeechRecognition()
    await roomRef.current?.disconnect()
    roomRef.current = null
    setConnected(false)
    setMicEnabled(true)
  }, [_stopSpeechRecognition])

  const sendToRoom = useCallback(async (payload) => {
    const room = roomRef.current
    if (!room) return
    try {
      await room.localParticipant.publishData(
        new TextEncoder().encode(JSON.stringify(payload)),
        { reliable: true },
      )
    } catch (_) {}
  }, [])

  return { connected, joining, micEnabled, joinCall, toggleMic, leaveCall, sendToRoom }
}
