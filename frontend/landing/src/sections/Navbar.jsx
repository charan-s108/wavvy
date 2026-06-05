import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronDown, Menu, X, Star } from 'lucide-react';
import { SiGithub } from 'react-icons/si';

const NAV_LINKS = [
  { name: 'AI Agents',  dropdown: true  },
  { name: 'Solutions',  dropdown: true  },
  { name: 'Customers',  dropdown: false },
  { name: 'Resources',  dropdown: true  },
  { name: 'Company',    dropdown: true  },
];

export default function Navbar({ onOpenCall }) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

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
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.5 }}
            className="hidden lg:block text-[14px] font-medium text-white/50 hover:text-brand-yellow transition-colors cursor-pointer px-2"
          >
            Login
          </motion.button>

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
              e.currentTarget.style.background = 'rgba(255,255,255,0.10)';
              e.currentTarget.style.borderColor = 'rgba(255,255,255,0.22)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
              e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)';
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
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.28 }}
              className="mt-8 grid grid-cols-1 gap-3"
            >
              <button className="w-full py-4 text-center glass rounded-2xl font-normal text-white/80 hover:bg-white/10 transition-colors">
                Login
              </button>
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
  );
}
