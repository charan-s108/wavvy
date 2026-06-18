import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronDown, Menu, X, Star, ExternalLink, Users, LayoutDashboard, AlertTriangle } from 'lucide-react';
import { SiGithub } from 'react-icons/si';

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || 'https://brocode12-wavvy.hf.space'
const AGENT_URL = 'https://wavvy-agent.vercel.app'
const ADMIN_URL = 'https://wavvy-admin-mu.vercel.app'

const NAV_LINKS = [
  { name: 'AI Agents',  dropdown: true  },
  { name: 'Solutions',  dropdown: true  },
  { name: 'Customers',  dropdown: false },
  { name: 'Resources',  dropdown: true  },
];

const PORTALS = [
  {
    label: 'Agent Console',
    desc:  'Live call handling + AI companion',
    href:  AGENT_URL,
    icon:  Users,
  },
  {
    label: 'Admin Dashboard',
    desc:  'QA scores, coaching, knowledge base',
    href:  ADMIN_URL,
    icon:  LayoutDashboard,
  },
]


// ── Portal dropdown ───────────────────────────────────────────────────────────

function PortalDropdown({ status }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const dot = status === 'online'
    ? 'bg-green-400'
    : status === 'offline'
    ? 'bg-red-400 animate-pulse'
    : 'bg-yellow-400 animate-pulse'

  const dotTitle = status === 'online'
    ? 'Backend online'
    : status === 'offline'
    ? 'Backend starting up (~30s)'
    : 'Checking backend…'

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 text-sm font-medium text-white/70 hover:text-white transition-colors group"
      >
        <span
          title={dotTitle}
          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`}
        />
        <span>Platform</span>
        <ChevronDown className={`w-3 h-3 text-white/40 group-hover:text-white/70 transition-all duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            className="absolute top-full right-0 mt-3 w-64 rounded-2xl overflow-hidden"
            style={{
              background: 'rgba(20,19,29,0.97)',
              border: '1px solid rgba(255,255,255,0.10)',
              boxShadow: '0 24px 48px rgba(0,0,0,0.6)',
              backdropFilter: 'blur(16px)',
            }}
          >
            {/* Backend status banner */}
            {status !== 'online' && (
              <div
                className="flex items-center gap-2 px-4 py-2.5 text-[11px]"
                style={{
                  background: status === 'offline'
                    ? 'rgba(252,83,91,0.12)'
                    : 'rgba(250,188,45,0.12)',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                  color: status === 'offline' ? '#fc535b' : '#fabc2d',
                }}
              >
                <AlertTriangle size={11} className="shrink-0" />
                {status === 'checking'
                  ? 'Checking backend status…'
                  : 'Backend starting up — login may take ~30s'}
              </div>
            )}

            <div className="p-2">
              {PORTALS.map(({ label, desc, href, icon: Icon }) => (
                <a
                  key={href}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setOpen(false)}
                  className="flex items-start gap-3 px-3 py-3 rounded-xl group transition-colors"
                  style={{ color: 'inherit' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.06)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                    style={{ background: 'rgba(244,247,61,0.10)' }}
                  >
                    <Icon size={14} className="text-brand-yellow" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-white">{label}</span>
                      <ExternalLink size={10} className="text-white/30 group-hover:text-white/60 transition-colors" />
                    </div>
                    <p className="text-[11px] text-white/40 mt-0.5 leading-relaxed">{desc}</p>
                  </div>
                </a>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Main Navbar ───────────────────────────────────────────────────────────────

export default function Navbar({ onOpenCall, backendStatus }) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const status = backendStatus ?? 'checking'

  const dot = status === 'online'
    ? 'bg-green-400'
    : status === 'offline'
    ? 'bg-red-400 animate-pulse'
    : 'bg-yellow-400 animate-pulse'

  return (
    <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 w-[95%] max-w-7xl">
      <motion.nav
        initial={{ opacity: 0, y: -24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="glass rounded-full px-3 md:px-8 py-1 md:py-4 flex items-center justify-between transition-all duration-300">
          {/* Logo */}
          <motion.div
            whileHover={{ scale: 1.04 }}
            className="flex items-center gap-1.5 md:gap-2 group cursor-pointer shrink-0"
          >
            <svg width="24" height="24" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="md:w-8 md:h-8 transition-transform duration-500 group-hover:rotate-12">
              <path d="M4 16C4 16 7 24 12 24C17 24 15 8 20 8C25 8 28 16 28 16" stroke="#F2F536" strokeWidth="4" strokeLinecap="round" />
            </svg>
            <span className="font-bold text-base md:text-xl tracking-tight uppercase">
              Wavvy<span className="text-brand-yellow">.</span>
            </span>
          </motion.div>

          {/* Desktop nav links */}
          <div className="hidden lg:flex items-center gap-8">
            {NAV_LINKS.map((link, i) => (
              <motion.div
                key={link.name}
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.1 + i * 0.07, ease: [0.16, 1, 0.3, 1] }}
                className="group relative flex items-center gap-1 cursor-pointer"
              >
                <span className="text-sm font-medium text-white/70 group-hover:text-white transition-colors">
                  {link.name}
                </span>
                {link.dropdown && (
                  <ChevronDown className="w-3 h-3 text-white/40 group-hover:text-white/70 transition-colors" />
                )}
                <div className="absolute -bottom-1 left-0 w-0 h-[1.5px] bg-brand-yellow group-hover:w-full transition-all duration-300" />
              </motion.div>
            ))}
          </div>

          {/* Right side */}
          <div className="flex items-center gap-2 md:gap-4 leading-none">
            {/* Platform dropdown (desktop) */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.45 }}
              className="hidden lg:block"
            >
              <PortalDropdown status={status} />
            </motion.div>

            <motion.a
              href="https://github.com/charan-s108/wavvy"
              target="_blank"
              rel="noopener noreferrer"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, delay: 0.55, ease: [0.16, 1, 0.3, 1] }}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="hidden sm:flex items-center gap-2 md:gap-2.5 px-4 md:px-6 py-2.5 md:py-3 rounded-full text-[13px] md:text-[14px] font-medium cursor-pointer whitespace-nowrap transition-colors"
              style={{
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.12)',
                color: 'rgba(255,255,255,0.85)',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.10)'
                e.currentTarget.style.borderColor = 'rgba(255,255,255,0.22)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.06)'
                e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)'
              }}
            >
              <SiGithub size={16} className="shrink-0" />
              <span>Star on GitHub</span>
              <span className="hidden md:flex items-center gap-1 pl-3 border-l border-white/15 ml-2 text-brand-yellow">
                <Star size={12} className="fill-brand-yellow" />
              </span>
            </motion.a>

            <button
              className="lg:hidden text-white p-2 hover:bg-white/5 rounded-full transition-colors"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            >
              <AnimatePresence mode="wait" initial={false}>
                {isMobileMenuOpen
                  ? <motion.span key="x" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.2 }}><X size={20} /></motion.span>
                  : <motion.span key="menu" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }} transition={{ duration: 0.2 }}><Menu size={20} /></motion.span>
                }
              </AnimatePresence>
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        <AnimatePresence>
          {isMobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -10 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="absolute top-full left-0 right-0 mt-3 mx-1 glass rounded-3xl p-8 lg:hidden border border-white/10 shadow-2xl origin-top"
            >
              {/* Backend status banner (mobile) */}
              {status !== 'online' && (
                <div
                  className="flex items-center gap-2 rounded-xl px-4 py-2.5 mb-6 text-[12px]"
                  style={{
                    background: status === 'offline' ? 'rgba(252,83,91,0.12)' : 'rgba(250,188,45,0.12)',
                    color: status === 'offline' ? '#fc535b' : '#fabc2d',
                    border: `1px solid ${status === 'offline' ? 'rgba(252,83,91,0.2)' : 'rgba(250,188,45,0.2)'}`,
                  }}
                >
                  <AlertTriangle size={12} className="shrink-0" />
                  {status === 'checking'
                    ? 'Checking backend status…'
                    : 'Backend starting up — login may take ~30 seconds'}
                </div>
              )}

              <div className="space-y-1">
                {NAV_LINKS.map((link, i) => (
                  <motion.div
                    key={link.name}
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.35, delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}
                    className="py-4 border-b border-white/5 flex items-center justify-between px-2 rounded-lg"
                  >
                    <span className="text-xl font-light tracking-wide">{link.name}</span>
                    {link.dropdown && <ChevronDown className="w-5 h-5 text-white/30" />}
                  </motion.div>
                ))}
              </div>

              {/* Portal links (mobile) */}
              <div className="mt-6 space-y-2">
                <p className="text-[11px] uppercase tracking-widest text-white/30 px-2 mb-3">Platform</p>
                {PORTALS.map(({ label, desc, href, icon: Icon }) => (
                  <a
                    key={href}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-3 px-3 py-3 rounded-xl"
                    style={{
                      background: 'rgba(255,255,255,0.04)',
                      border: '1px solid rgba(255,255,255,0.07)',
                    }}
                    onClick={() => setIsMobileMenuOpen(false)}
                  >
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: 'rgba(244,247,61,0.10)' }}
                    >
                      <Icon size={14} className="text-brand-yellow" />
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium text-white">{label}</span>
                        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
                      </div>
                      <p className="text-[11px] text-white/40">{desc}</p>
                    </div>
                  </a>
                ))}
              </div>

              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: 0.28 }}
                className="mt-6"
              >
                <a
                  href="https://github.com/charan-s108/wavvy"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full py-4 flex items-center justify-center gap-3 rounded-2xl font-normal transition-all"
                  style={{
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    color: 'rgba(255,255,255,0.85)',
                  }}
                >
                  <SiGithub size={18} />
                  <span>Star on GitHub</span>
                  <Star size={13} className="fill-brand-yellow text-brand-yellow" />
                </a>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.nav>
    </div>
  )
}
