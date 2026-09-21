import type { Variants } from 'framer-motion';

// Enforce strict animation durations: 150ms (micro), 250ms (standard), 400ms (complex)

export const transitions = {
  micro: { type: "tween", duration: 0.15, ease: "easeOut" },
  standard: { type: "tween", duration: 0.25, ease: [0.25, 0.1, 0.25, 1.0] }, // Smooth standard curve
  complex: { type: "spring", stiffness: 260, damping: 20 },
  slow: { type: "tween", duration: 0.4, ease: "easeInOut" }
} as const;

export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: { 
    opacity: 1, 
    y: 0, 
    transition: transitions.standard 
  },
  exit: {
    opacity: 0,
    y: -10,
    transition: transitions.micro
  }
};

export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05,
      delayChildren: 0.1
    }
  }
};

export const scaleUp: Variants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: transitions.complex
  },
  exit: {
    opacity: 0,
    scale: 0.95,
    transition: transitions.micro
  }
};

export const glassMorph: Variants = {
  hidden: { opacity: 0, backdropFilter: "blur(0px)" },
  visible: {
    opacity: 1,
    backdropFilter: "blur(16px)",
    transition: transitions.slow
  }
};

export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 50 },
  visible: {
    opacity: 1,
    x: 0,
    transition: transitions.standard
  }
};
