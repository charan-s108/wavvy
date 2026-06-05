import React from 'react';
import { motion, useScroll, useTransform } from 'motion/react';

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.13, delayChildren: 0.1 } },
}

const item = {
  hidden: { opacity: 0, y: 48 },
  visible: { opacity: 1, y: 0, transition: { duration: 1.1, ease: [0.16, 1, 0.3, 1] } },
}

export default function Hero({ onOpenCall }) {
  const { scrollY } = useScroll();
  const sphereOpacity    = useTransform(scrollY, [0, 500], [1, 0]);
  const atmosphereOpacity = useTransform(scrollY, [0, 500], [0.3, 0]);

  return (
    <section className="section_hero relative min-h-screen pt-[38vh] md:pt-[30vh] pb-10 md:pb-16 px-6 overflow-hidden flex flex-col items-center bg-black">

      {/* ── Background layer ── */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">

        {/* Stars */}
        <div className="absolute inset-0 opacity-40">
          {[...Array(80)].map((_, i) => (
            <motion.div
              key={i}
              initial={{ opacity: Math.random() * 0.5 + 0.2 }}
              animate={{ opacity: [0.2, 0.8, 0.2] }}
              transition={{
                duration: 4 + Math.random() * 6,
                repeat: Infinity,
                ease: 'easeInOut',
                delay: Math.random() * 5,
              }}
              className="absolute rounded-full bg-white"
              style={{
                width:  Math.random() * 1.5 + 'px',
                height: Math.random() * 1.5 + 'px',
                top:  Math.random() * 100 + '%',
                left: Math.random() * 100 + '%',
              }}
            />
          ))}
        </div>

        {/* Sphere — centering wrapper owns horizontal placement, motion owns y/opacity */}
        <div className="absolute inset-x-0 top-[12%] md:top-[-5%] flex justify-center z-10">
          <motion.div
            initial={{ y: 300, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 1.8, ease: [0.16, 1, 0.3, 1] }}
            style={{ opacity: sphereOpacity }}
            className="w-[180vw] md:w-[130vw] aspect-square flex-shrink-0"
          >
            <div className="relative w-full">
              <img
                src="https://cdn.prod.website-files.com/5caac3a8d636b7cfc2606d35/69e0f259e4414abe7eb382c9_Clip%20path%20group.png"
                alt=""
                className="w-full h-auto object-contain glow-image mix-blend-screen"
                loading="lazy"
              />
              <div className="glow absolute top-[30%] left-1/2 -translate-x-1/2 w-[50%] h-[30%] bg-brand-yellow/20 blur-[120px] rounded-full" />
            </div>
          </motion.div>
        </div>

        {/* Atmosphere glow */}
        <motion.div
          style={{ opacity: atmosphereOpacity }}
          className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-[600px] bg-brand-yellow/5 blur-[120px]"
        />
      </div>

      {/* ── Foreground layer ── */}
      <div className="container-large max-w-7xl mx-auto w-full relative z-10">
        <div className="home_hero-wrapper flex flex-col items-center">
          <motion.div
            variants={container}
            initial="hidden"
            animate="visible"
            className="hero_content text-center"
          >
            {/* Eyebrow */}
            <motion.div variants={item} className="eyebrow_container mb-4 md:mb-12">
              <div className="inline-flex items-center px-1.5 py-0.5 md:px-4 md:py-2 border border-white/10 rounded-full bg-white/5 backdrop-blur-sm shadow-[0_4px_24px_rgba(0,0,0,0.5)]">
                <p className="text-[7px] md:text-[10px] font-medium uppercase tracking-[0.4em] text-white/50 font-inter">
                  Agentic AI for Customer experience
                </p>
              </div>
            </motion.div>

            {/* Headline */}
            <motion.h1
              variants={item}
              className="font-display tracking-tight mb-4 md:mb-10 flex flex-col items-center"
            >
              <span className="text-3xl sm:text-5xl md:text-7xl lg:text-8xl leading-[1.1] font-light block">
                Purpose-Built{' '}
                <span className="text-brand-yellow text-glow font-light">AI Agents.</span>
              </span>
              <span className="text-3xl sm:text-5xl md:text-7xl lg:text-8xl leading-[1.1] font-light block text-[#efefef]">
                One CX Platform.
              </span>
            </motion.h1>

            {/* Sub-text */}
            <motion.p
              variants={item}
              className="text-[13px] md:text-2xl text-white/50 max-w-2xl mx-auto mb-6 md:mb-16 leading-relaxed font-sans font-light tracking-[0.024px] px-4"
            >
              Wavvy's Agentic CX Platform uses AI Agents to resolve interactions and improve CX outcomes
            </motion.p>

            {/* CTA buttons */}
            <motion.div
              variants={item}
              className="flex flex-row items-center justify-center gap-2 md:gap-6 px-2 mb-1"
            >
              <motion.button
                onClick={onOpenCall}
                whileHover={{ scale: 1.03, y: -2 }}
                whileTap={{ scale: 0.97 }}
                className="bg-brand-yellow text-black px-3 py-2 md:px-12 md:py-5 rounded-full font-normal text-[11px] md:text-[18px] shadow-[0_15px_40px_rgba(242,245,54,0.3)] cursor-pointer min-w-[100px] md:min-w-[200px] text-center"
              >
                Request demo
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.03, y: -2 }}
                whileTap={{ scale: 0.97 }}
                className="glass border-white/20 px-3 py-2 md:px-12 md:py-5 rounded-full font-normal text-[11px] md:text-[18px] flex items-center justify-center gap-1 md:gap-2 hover:bg-white/10 transition-colors cursor-pointer min-w-[100px] md:min-w-[200px] text-white text-center"
              >
                Our platform
              </motion.button>
            </motion.div>
          </motion.div>
        </div>
      </div>

      <div className="h-24 md:h-32" />
    </section>
  );
}
