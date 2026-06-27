import type { ReactNode } from 'react';

type Tone = 'cream' | 'white';

interface Props {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  id?: string;
  /** Override the inner vertical padding (defaults to the standard band spacing). */
  padY?: string;
}

const TONES: Record<Tone, string> = {
  cream: 'bg-bg',
  white: 'bg-surface',
};

/**
 * Full-bleed section band. The page stacks these to create the alternating
 * cream / white horizontal bands of the veto-style landing layout.
 * Content is constrained to a centered max-width container and left-aligned.
 */
export default function Section({
  children,
  tone = 'cream',
  className = '',
  id,
  padY = 'py-20 sm:py-28',
}: Props) {
  return (
    <section id={id} className={`w-full ${TONES[tone]} ${className}`}>
      <div className={`mx-auto max-w-6xl px-6 ${padY}`}>{children}</div>
    </section>
  );
}
