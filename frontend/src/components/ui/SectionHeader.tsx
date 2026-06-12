interface Props {
  title: string;
  className?: string;
}

/**
 * Canonical uppercase section heading — consistent across all pages and drawers.
 */
export default function SectionHeader({ title, className = '' }: Props) {
  return (
    <h4
      className={`text-[11px] font-semibold uppercase tracking-widest text-ink-faint ${className}`}
    >
      {title}
    </h4>
  );
}
