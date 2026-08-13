import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'outline' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-grad-accent text-ink border-transparent shadow-glow hover:shadow-glow-lg hover:brightness-105',
  outline: 'bg-surface text-ink hover:bg-surface-subtle hover:border-accent/40 border-border-strong shadow-sm',
  ghost:   'bg-transparent text-ink-muted hover:bg-surface-subtle border-transparent',
  danger:  'bg-surface text-[var(--s-failed-text)] hover:bg-[var(--s-failed-bg)] border-[var(--s-failed-border)] shadow-sm',
};

const SIZES: Record<Size, string> = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3.5 py-1.5 text-sm',
  lg: 'px-5 py-2.5 text-sm',
};

export default function Button({
  variant = 'outline',
  size = 'md',
  className = '',
  children,
  disabled,
  ...rest
}: Props) {
  return (
    <button
      type="button"
      disabled={disabled}
      className={`inline-flex items-center justify-center rounded-full border font-semibold transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
