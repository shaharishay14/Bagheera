import type { ReactNode } from 'react';
import { motion } from 'framer-motion';

interface Props {
  children: ReactNode;
  className?: string;
  /** Stagger delay in seconds for reveals that fire in sequence. */
  delay?: number;
}

/**
 * Scroll-reveal wrapper: fades in with a slight upward rise the first time the
 * element enters the viewport. The shared motion primitive for the veto-style
 * landing bands so every section animates identically.
 */
export default function Reveal({ children, className = '', delay = 0 }: Props) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay }}
    >
      {children}
    </motion.div>
  );
}
