import React from 'react';
import { motion } from 'motion/react';
import { SiOpenai, SiReact, SiTailwindcss, SiPython, SiFastapi, SiPostgresql, SiHuggingface } from 'react-icons/si';
import { Database, Mic2, Zap, Network, Target, Component, Cpu, GitBranch } from 'lucide-react';

const TECH_STACK = [
  { name: 'React',           icon: SiReact       },
  { name: 'Tailwind CSS',    icon: SiTailwindcss  },
  { name: 'Framer Motion',   icon: Cpu            },
  { name: 'Python',          icon: SiPython       },
  { name: 'FastAPI',         icon: SiFastapi      },
  { name: 'Uvicorn',         icon: Zap            },
  { name: 'PostgreSQL',      icon: SiPostgresql   },
  { name: 'OpenAI',          icon: SiOpenai       },
  { name: 'Hugging Face',    icon: SiHuggingface  },
  { name: 'ChromaDB',        icon: Database       },
  { name: 'Hybrid RAG',      icon: Component      },
  { name: 'Cartesia AI',     icon: Mic2           },
  { name: 'Vector Search',   icon: Target         },
  { name: 'Graph Retrieval', icon: Network        },
  { name: 'BM25',            icon: GitBranch      },
];

export default function TechStrip() {
  return (
    <motion.section
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      transition={{ duration: 1, ease: 'easeOut' }}
      viewport={{ once: true, margin: '-60px' }}
      className="relative py-14 md:py-20 overflow-hidden"
    >
      {/* Edge fades */}
      <div className="absolute inset-y-0 left-0 w-32 md:w-52 bg-gradient-to-r from-black to-transparent z-20 pointer-events-none" />
      <div className="absolute inset-y-0 right-0 w-32 md:w-52 bg-gradient-to-l from-black to-transparent z-20 pointer-events-none" />


      {/* Marquee */}
      <div className="overflow-hidden">
        <motion.div
          animate={{ x: ['0%', '-33.333%'] }}
          transition={{ duration: 55, repeat: Infinity, ease: 'linear' }}
          className="flex w-max items-center gap-8 md:gap-24"
        >
          {[...TECH_STACK, ...TECH_STACK, ...TECH_STACK].map((tech, i) => {
            const Icon = tech.icon;
            return (
              <motion.div
                key={`${tech.name}-${i}`}
                whileHover={{ scale: 1.12 }}
                transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                className="group flex items-center gap-2 md:gap-4 shrink-0 cursor-default"
              >
                {Icon && (
                  <div className="flex h-6 w-6 md:h-10 md:w-10 items-center justify-center">
                    <Icon
                      size={20}
                      className="text-brand-yellow/60 group-hover:text-brand-yellow transition-colors duration-300 md:w-7 md:h-7"
                    />
                  </div>
                )}
                <span className="text-sm md:text-2xl font-light tracking-tight text-white/45 group-hover:text-white transition-colors duration-300 whitespace-nowrap">
                  {tech.name}
                </span>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </motion.section>
  );
}
