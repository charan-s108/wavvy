import React from 'react';
import { motion } from 'motion/react';
import { Twitter, Linkedin, Github } from 'lucide-react';

const SOCIALS = [
  { Icon: Linkedin, href: 'https://linkedin.com/in/charan-s108' },
  { Icon: Github,   href: 'https://github.com/charan-s108' },
  { Icon: Twitter,  href: 'https://twitter.com/charan_s108' },
];

export default function Footer() {
  return (
    <footer className="pt-24 pb-12 px-6 border-t border-white/5 relative z-10 bg-black">
      <div className="max-w-7xl mx-auto flex flex-col items-center text-center">

        {/* Logo */}
        <motion.span
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          viewport={{ once: true, margin: '-40px' }}
          className="font-bold text-3xl tracking-tighter uppercase font-sans text-white mb-6 block"
        >
          Wavvy<span className="text-brand-yellow">.</span>
        </motion.span>

        {/* Tagline */}
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          viewport={{ once: true, margin: '-40px' }}
          className="text-white/40 mb-8 font-light leading-relaxed max-w-md"
        >
          Automating the world's customer operations with high-fidelity AI agents that learn, adapt, and scale infinitely.
        </motion.p>

        {/* Social icons */}
        <div className="flex gap-4 mb-12">
          {SOCIALS.map(({ Icon, href }, i) => (
            <motion.a
              key={i}
              href={href}
              target={href.startsWith('http') ? '_blank' : undefined}
              rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
              initial={{ opacity: 0, scale: 0.7 }}
              whileInView={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, delay: 0.2 + i * 0.08, ease: [0.16, 1, 0.3, 1] }}
              whileHover={{ scale: 1.15, borderColor: 'rgba(244,247,61,0.5)', color: '#f4f73d' }}
              whileTap={{ scale: 0.92 }}
              viewport={{ once: true, margin: '-40px' }}
              className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center text-white/40 bg-white/5 transition-colors"
            >
              <Icon size={20} />
            </motion.a>
          ))}
        </div>

        {/* Bottom bar */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          transition={{ duration: 1, delay: 0.35, ease: 'easeOut' }}
          viewport={{ once: true, margin: '-40px' }}
          className="pt-10 border-t border-white/5 w-full flex flex-col md:flex-row items-center justify-between gap-6"
        >
          <p className="text-white/50 text-xs md:text-sm font-light">
            © 2026 Wavvy Platform Inc. All rights reserved.
          </p>
          <p className="text-white/50 text-xs md:text-sm font-light">
            Crafted with 💛 by{' '}
            <motion.a
              href="https://github.com/charan-s108"
              target="_blank"
              rel="noopener noreferrer"
              whileHover={{ color: '#f4f73d' }}
              className="text-white/75 transition-colors font-medium"
            >
              Charan S
            </motion.a>
          </p>
        </motion.div>
      </div>
    </footer>
  );
}
