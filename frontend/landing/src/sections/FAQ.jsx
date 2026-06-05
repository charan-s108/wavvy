import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Plus, Minus } from 'lucide-react';

const FAQS = [
  {
    question: 'How do AI agents integrate with our existing CX stack?',
    answer: 'AI customer service Agents connect to your CRM, CCaaS, knowledge base, and backend systems to read and write data, trigger workflows, and operate within your existing environment seamlessly.',
  },
  {
    question: 'How do you ensure accuracy and compliance?',
    answer: 'AI support Agents follow structured workflows with enforced steps for authentication, disclosures, and policy adherence, with built-in evaluation and auditability across every interaction.',
  },
  {
    question: 'How quickly can we deploy AI Agents?',
    answer: 'Most teams go from initial setup to production in a month or two, using pre-built workflows, integrations, and testing tools to accelerate deployment.',
  },
  {
    question: 'How do all the AI agents work together across the platform?',
    answer: 'Customer, frontline, and operations agents share the same data, context, and workflows, so every interaction, action, and insight feeds into a single, unified CX intelligence system.',
  },
  {
    question: 'What level of visibility do we get into performance?',
    answer: 'You can evaluate 100% of interactions, track performance in real time, and surface trends across customers, agents, and operations with our integrated analytics dashboard.',
  },
  {
    question: 'How do you maintain control and governance at scale?',
    answer: 'The platform enforces strict policies, tracks every action, and provides full visibility into performance, so enterprise teams can operate with total control as AI agents take on more work.',
  },
];

export default function FAQ() {
  const [activeIndex, setActiveIndex] = useState(null);

  return (
    <section className="pt-8 md:pt-12 pb-8 md:pb-12 px-6 relative">
      <div className="max-w-5xl mx-auto">

        {/* Heading */}
        <div className="text-center mb-16 md:mb-24">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true, margin: '-40px' }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-brand-yellow/20 bg-brand-yellow/5 mb-6"
          >
            <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-brand-yellow">Resources</span>
          </motion.div>

          <motion.h2
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true, margin: '-40px' }}
            className="text-3xl md:text-6xl lg:text-7xl font-display font-light text-white mb-6 tracking-tight leading-[1.1]"
          >
            Frequently Asked <span className="italic text-brand-yellow">Questions</span>
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.16, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true, margin: '-40px' }}
            className="text-white/40 font-light text-lg"
          >
            Everything you need to know about implementing enterprise AI.
          </motion.p>
        </div>

        {/* FAQ items */}
        <div className="space-y-0">
          {FAQS.map((faq, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] }}
              viewport={{ once: true, margin: '-20px' }}
              className="border-b border-white/5 last:border-0"
            >
              <button
                onClick={() => setActiveIndex(activeIndex === i ? null : i)}
                className="w-full flex items-center justify-between py-8 text-left group transition-all"
              >
                <span className={`text-lg md:text-xl font-light transition-all duration-300 ${
                  activeIndex === i ? 'text-white' : 'text-white/60 group-hover:text-white'
                }`}>
                  {faq.question}
                </span>
                <motion.div
                  animate={{ rotate: activeIndex === i ? 180 : 0 }}
                  transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  className={`ml-4 flex-shrink-0 ${activeIndex === i ? 'text-brand-yellow' : 'text-white/20 group-hover:text-white/40'}`}
                >
                  {activeIndex === i
                    ? <Minus size={20} strokeWidth={1.5} />
                    : <Plus size={20} strokeWidth={1.5} />
                  }
                </motion.div>
              </button>

              <AnimatePresence initial={false}>
                {activeIndex === i && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                    className="overflow-hidden"
                  >
                    <motion.div
                      initial={{ y: -8 }}
                      animate={{ y: 0 }}
                      exit={{ y: -8 }}
                      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                      className="pb-8"
                    >
                      <p className="text-white/40 font-light leading-relaxed text-base md:text-lg max-w-2xl">
                        {faq.answer}
                      </p>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
