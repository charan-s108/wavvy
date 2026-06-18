import { useState, useEffect, useRef } from 'react'
import Navbar from './sections/Navbar.jsx'
import Hero from './sections/Hero.jsx'
import TechStrip from './sections/TechStrip.jsx'
import Features from './sections/Features.jsx'
import FAQ from './sections/FAQ.jsx'
import CTA from './sections/CTA.jsx'
import Footer from './sections/Footer.jsx'
import CallButton from './call-modal/CallButton.jsx'
import CallModal from './call-modal/CallModal.jsx'

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || 'https://brocode12-wavvy.hf.space'

// Warm up the backend on page load and keep polling until online.
// Retry every 12s, give up after ~2 minutes.
function useBackendStatus() {
  const [status, setStatus] = useState('checking')
  const timerRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    let attempt = 0
    const MAX = 12

    const check = async () => {
      try {
        const res = await fetch(`${BACKEND}/api/health`, {
          signal: AbortSignal.timeout(9000),
        })
        if (cancelled) return
        if (res.ok) { setStatus('online'); return }
      } catch {
        if (cancelled) return
      }
      setStatus('offline')
      attempt++
      if (attempt < MAX) {
        timerRef.current = setTimeout(check, 12000)
      }
    }

    check()
    return () => {
      cancelled = true
      clearTimeout(timerRef.current)
    }
  }, [])

  return status
}

export default function App() {
  const [modalOpen, setModalOpen] = useState(false)
  const backendStatus = useBackendStatus()
  const open = () => setModalOpen(true)
  const close = () => setModalOpen(false)

  return (
    <div className="relative min-h-screen bg-black overflow-x-hidden">
      <Navbar onOpenCall={open} backendStatus={backendStatus} />

      <main className="relative z-10">
        <Hero onOpenCall={open} />
        <TechStrip />
        <Features />
        <FAQ />
        <CTA onOpenCall={open} />
      </main>

      <Footer />

      <CallButton onClick={open} />
      <CallModal open={modalOpen} onClose={close} backendStatus={backendStatus} />
    </div>
  )
}
