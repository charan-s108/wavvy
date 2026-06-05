import React from 'react';
import { motion } from 'motion/react';

const FEATURES = [
  {
    title: 'AI Agents for Customers',
    description: 'Resolve customer inquiries end-to-end across voice and chat, from authentication to execution',
    videoUrl: '/UI 1.mp4',
    accent: '#f4f73d',
  },
  {
    title: 'AI Agents for Frontline Teams',
    description: 'Guide every interaction in real-time with personalized context, next-best action, and automated actions',
    videoUrl: '/UI 2.mp4',
    accent: '#f4f73d',
  },
  {
    title: 'AI Agents for Operations',
    description: 'Evaluate interactions, generate coaching, and surface insights to take action across your entire operation',
    videoUrl: '/UI 3.mp4',
    accent: '#f4f73d',
  },
];

const cardVariants = {
  hidden: { opacity: 0, y: 48 },
  visible: (i) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 1, delay: i * 0.12, ease: [0.16, 1, 0.3, 1] },
  }),
};

export default function Features() {
  return (
    <section className="section_how-do-we-help pt-10 md:pt-24 pb-12 md:pb-16 px-6 overflow-hidden">
      <div className="max-w-7xl mx-auto">

        {/* Heading */}
        <div className="text-center mb-10 md:mb-24 relative">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true, margin: '-40px' }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-brand-yellow/20 bg-brand-yellow/5 mb-6"
          >
            <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-brand-yellow">
              Platform
            </span>
          </motion.div>

          <motion.h2
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true, margin: '-40px' }}
            className="font-display text-3xl md:text-6xl lg:text-7xl leading-[1.1] font-light mb-4 text-center tracking-tight"
          >
            What We Do &amp; How <br className="hidden md:block" />
            We <span className="text-brand-yellow italic">Transform CX</span>
          </motion.h2>
        </div>

        {/* Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
          {FEATURES.map((feature, i) => (
            <motion.div
              key={feature.title}
              custom={i}
              variants={cardVariants}
              initial="hidden"
              whileInView="visible"
              whileHover={{ y: -6, transition: { type: 'spring', stiffness: 300, damping: 20 } }}
              viewport={{ once: true, margin: '-40px' }}
              className="card_vertical group relative flex flex-col bg-transparent border border-brand-yellow/25 rounded-[24px] overflow-hidden"
              style={{ '--accent': feature.accent }}
            >
              {/* Top accent line animates in on hover */}
              <motion.div
                className="absolute top-0 left-0 right-0 h-px z-10"
                style={{ background: `linear-gradient(90deg, transparent, ${feature.accent}80, transparent)` }}
                initial={{ scaleX: 0, opacity: 0 }}
                whileInView={{ scaleX: 1, opacity: 1 }}
                transition={{ duration: 1, delay: 0.3 + i * 0.1, ease: [0.16, 1, 0.3, 1] }}
                viewport={{ once: true }}
              />

              <div className="px-6 md:px-8 pt-8 md:pt-10 pb-4 text-center">
                <h3 className="text-[20px] md:text-[22px] leading-tight font-sans font-medium mb-3 tracking-tight text-[#efefef]">
                  {feature.title}
                </h3>
                <p className="text-[14px] md:text-[15px] text-white/50 leading-relaxed font-light">
                  {feature.description}
                </p>
              </div>

              <div className="card_graphics-wrapper relative w-full aspect-[4/5] overflow-hidden flex items-start justify-center">
                <motion.video
                  src={feature.videoUrl}
                  autoPlay
                  loop
                  muted
                  playsInline
                  initial={{ scale: 1.05, opacity: 0.7 }}
                  whileInView={{ scale: 1, opacity: 0.9 }}
                  whileHover={{ opacity: 1 }}
                  transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
                  viewport={{ once: true }}
                  className="w-full h-full object-contain select-none pointer-events-none"
                />
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
