import React from 'react';
import { motion } from 'motion/react';

export default function CTA({ onOpenCall }) {
  return (
    <section className="pt-4 md:pt-6 pb-12 md:pb-20 px-6 relative overflow-hidden">
      <div className="max-w-4xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          viewport={{ once: true, margin: '-60px' }}
          className="relative glass p-12 md:p-20 rounded-[32px] border-white/10 text-center overflow-hidden"
        >
          {/* Radial glow behind content */}
          <motion.div
            initial={{ opacity: 0, scale: 0.6 }}
            whileInView={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.4, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true }}
            className="absolute inset-0 pointer-events-none"
            style={{
              background: 'radial-gradient(ellipse 60% 50% at 50% 100%, rgba(244,247,61,0.07) 0%, transparent 70%)',
            }}
          />

          <motion.h2
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true }}
            className="text-2xl md:text-5xl lg:text-6xl font-display font-light mb-6 text-white leading-[1.1] tracking-tight relative z-10"
          >
            Ready to scale your{' '}
            <span className="italic text-brand-yellow">CX operations?</span>
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.18, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true }}
            className="text-white/40 mb-10 max-w-xl mx-auto font-light relative z-10"
          >
            Deploy enterprise-ready AI agents in weeks, not months.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.26, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true }}
            className="relative z-10"
          >
            <motion.button
              onClick={onOpenCall}
              whileHover={{ scale: 1.05, boxShadow: '0 20px 60px rgba(244,247,61,0.35)' }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 400, damping: 20 }}
              className="bg-brand-yellow text-black px-10 py-4 rounded-full font-bold text-lg shadow-xl shadow-brand-yellow/10 cursor-pointer"
            >
              Get Started
            </motion.button>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
