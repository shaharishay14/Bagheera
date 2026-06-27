import type { ReactNode } from 'react';
import { FiImage, FiDatabase, FiArchive } from 'react-icons/fi';
import Reveal from './Reveal';

/**
 * The three .env paths a user actually sets. Everything else (the /data and
 * /state/... names used inside the container) is wired up automatically by
 * docker-compose, so it is intentionally left out here.
 *
 * SOURCE OF TRUTH: docs/env-paths.md (section 2A, "Host-side variables").
 */

interface EnvPath {
  variable: string;
  badge: string;
  badgeTone: 'input' | 'state' | 'output';
  icon: ReactNode;
  title: string;
  body: string;
  /** What lives here, as short chips. */
  holds: string[];
  /** Disk recommendation. */
  disk: string;
}

const PATHS: EnvPath[] = [
  {
    variable: 'WSI_DATA_DIR',
    badge: 'Input',
    badgeTone: 'input',
    icon: <FiImage className="h-6 w-6" />,
    title: 'Your slides & manifest',
    body: 'Point this at the folder holding your whole-slide images and the manifest CSV. Bagheera reads from here (read-only), so your originals are never changed.',
    holds: ['Whole-slide images', 'manifest.csv'],
    disk: 'Wherever your slides already live',
  },
  {
    variable: 'STATE_DIR_INTERNAL',
    badge: 'App data',
    badgeTone: 'state',
    icon: <FiDatabase className="h-6 w-6" />,
    title: 'Database & model cache',
    body: "Bagheera's own working storage: the database that tracks your runs and the downloaded model weights. Small but read often.",
    holds: ['SQLite database', 'Model weights'],
    disk: 'Fast / local disk',
  },
  {
    variable: 'STATE_DIR_EXTERNAL',
    badge: 'Results',
    badgeTone: 'output',
    icon: <FiArchive className="h-6 w-6" />,
    title: 'Everything Bagheera produces',
    body: 'Where all your outputs are saved. This is the folder you back up and browse when you want your results.',
    holds: ['TRIDENT features', 'K-fold splits', 'Trained models', 'Visualizations', 'Inference outputs'],
    disk: 'Big / bulk-storage disk',
  },
];

const BADGE_TONES: Record<EnvPath['badgeTone'], string> = {
  input: 'bg-accent-muted text-accent-text',
  state: 'bg-surface-subtle text-ink-muted',
  output: 'bg-accent text-ink',
};

export default function EnvPathsDiagram() {
  return (
    <Reveal className="mt-12">
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {PATHS.map((p) => (
          <PathCard key={p.variable} path={p} />
        ))}
      </div>

      {/* Plain-language footnote: the concept, without the jargon. */}
      <div className="mt-6 flex flex-col gap-3 rounded-xl border border-accent/40 bg-accent-muted/60 p-5 sm:flex-row sm:items-start">
        <span className="inline-flex shrink-0 items-center rounded-full bg-accent px-2.5 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-ink">
          That&apos;s all
        </span>
        <p className="text-sm leading-relaxed text-ink-muted">
          These three folders stay on your machine. Docker just gets a window into them, so
          anything Bagheera saves appears in the same folder on your disk. You set these once in{' '}
          <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-xs text-ink">.env</code>;
          everything else is handled automatically. Inside the app you&apos;ll see short names like{' '}
          <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-xs text-ink">/data</code>.
          That&apos;s just how the container refers to your{' '}
          <span className="font-semibold text-ink">WSI_DATA_DIR</span> folder.
        </p>
      </div>
    </Reveal>
  );
}

function PathCard({ path }: { path: EnvPath }) {
  const { variable, badge, badgeTone, icon, title, body, holds, disk } = path;
  return (
    <div className="flex flex-col rounded-2xl border border-border bg-surface p-6 shadow-card">
      <div className="flex items-center justify-between">
        <span className="grid h-11 w-11 place-items-center rounded-lg bg-accent-muted text-accent-text">
          {icon}
        </span>
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-1 text-[0.65rem] font-bold uppercase tracking-wide ${BADGE_TONES[badgeTone]}`}
        >
          {badge}
        </span>
      </div>

      <code className="mt-5 block font-mono text-sm font-semibold text-ink">{variable}</code>
      <h3 className="mt-1 text-base font-bold tracking-tight text-ink">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">{body}</p>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {holds.map((h) => (
          <span
            key={h}
            className="rounded-md border border-border bg-surface-subtle px-2 py-0.5 text-xs font-medium text-ink-muted"
          >
            {h}
          </span>
        ))}
      </div>

      <p className="mt-auto pt-4 text-xs font-medium uppercase tracking-wide text-ink-faint">
        {disk}
      </p>
    </div>
  );
}
