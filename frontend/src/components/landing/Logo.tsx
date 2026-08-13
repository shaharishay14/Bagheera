import { useState } from 'react';

interface Props {
  /**
   * 'full' renders the complete stacked lockup (panther over wordmark) — used
   * big in the hero. 'horizontal' crops to just the panther shield + a text
   * wordmark, matching the navbar, for compact spots like the footer.
   */
  variant?: 'full' | 'horizontal';
  /** Tailwind height class for the <img> logo in 'full' mode, e.g. "h-44". */
  imgClassName?: string;
  /** Tailwind size classes for the gradient "B" mark fallback. */
  markClassName?: string;
  /** Tailwind text classes for the wordmark fallback / horizontal wordmark. */
  wordClassName?: string;
}

/**
 * Bagheera logo with graceful fallback. Tries /bagheera_logo.png first and, on
 * load error, swaps to the gradient "B" mark + wordmark — the same approach the
 * navbar in App.tsx uses, lifted here so the hero and footer share it.
 */
export default function Logo({
  variant = 'full',
  imgClassName = 'h-12 w-auto',
  markClassName = 'h-10 w-10 text-base',
  wordClassName = 'text-2xl',
}: Props) {
  const [logoOk, setLogoOk] = useState(true);

  // Horizontal lockup: crop the stacked asset down to the shield, pair with text.
  if (variant === 'horizontal') {
    return (
      <span className="flex items-center gap-2.5">
        {logoOk ? (
          <span className="flex h-9 w-10 items-start justify-center overflow-hidden">
            <img
              src="/bagheera_logo.png"
              alt=""
              aria-hidden
              className="h-[3.4rem] w-auto max-w-none"
              onError={() => setLogoOk(false)}
            />
          </span>
        ) : (
          <span
            className={`grid place-items-center rounded-lg bg-grad-brand font-black text-white shadow-glow ${markClassName}`}
          >
            B
          </span>
        )}
        <span className={`font-extrabold tracking-tight text-ink ${wordClassName}`}>
          Bagheera
        </span>
      </span>
    );
  }

  if (logoOk) {
    return (
      <img
        src="/bagheera_logo.png"
        alt="Bagheera"
        className={imgClassName}
        onError={() => setLogoOk(false)}
      />
    );
  }

  return (
    <span className="flex items-center gap-2.5">
      <span
        className={`grid place-items-center rounded-lg bg-grad-brand font-black text-white shadow-glow ${markClassName}`}
      >
        B
      </span>
      <span className={`font-extrabold tracking-tight text-ink ${wordClassName}`}>
        Bagheera
      </span>
    </span>
  );
}
