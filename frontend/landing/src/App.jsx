import { useState } from 'react'
import Navbar from './sections/Navbar.jsx'
import Hero from './sections/Hero.jsx'
import TechStrip from './sections/TechStrip.jsx'
import Features from './sections/Features.jsx'
import FAQ from './sections/FAQ.jsx'
import CTA from './sections/CTA.jsx'
import Footer from './sections/Footer.jsx'
import CallButton from './call-modal/CallButton.jsx'
import CallModal from './call-modal/CallModal.jsx'

export default function App() {
  const [modalOpen, setModalOpen] = useState(false)
  const open = () => setModalOpen(true)
  const close = () => setModalOpen(false)

  return (
    <div className="relative min-h-screen bg-black overflow-x-hidden">
      <Navbar onOpenCall={open} />

      <main className="relative z-10">
        <Hero onOpenCall={open} />
        <TechStrip />
        <Features />
        <FAQ />
        <CTA onOpenCall={open} />
      </main>

      <Footer />

      <CallButton onClick={open} />
      <CallModal open={modalOpen} onClose={close} />
    </div>
  )
}
