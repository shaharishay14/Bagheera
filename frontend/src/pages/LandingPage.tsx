import type { ReactNode } from 'react';
import { useState } from 'react';
import type { IconType } from 'react-icons';
import {
  SiReact,
  SiFastapi,
  SiPython,
  SiDocker,
  SiSqlite,
  SiVite,
  SiTailwindcss,
} from 'react-icons/si';
import { FaGithub, FaLinkedin } from 'react-icons/fa6';
import { FiCpu, FiScissors, FiLayers, FiPlay } from 'react-icons/fi';
import Section from '../components/landing/Section';
import SectionLabel from '../components/landing/SectionLabel';
import CTAButton from '../components/landing/CTAButton';
import Reveal from '../components/landing/Reveal';
import Logo from '../components/landing/Logo';
import EnvPathsDiagram from '../components/landing/EnvPathsDiagram';

const GITHUB_URL = 'https://github.com/shaharishay14/Bagheera';

interface Person {
  name: string;
  url: string;
}

const TEAM: Person[] = [
  { name: 'Shahar Ishay', url: 'https://www.linkedin.com/in/shahar-ishay-831762303/' },
  { name: 'Daniel Rubinstein', url: 'https://www.linkedin.com/in/daniel-rubinstein-900842398/' },
  { name: 'Dolfin Varshev', url: 'https://www.linkedin.com/in/dolfin-varshev/' },
];

/**
 * Bagheera marketing landing page. Veto-style alternating cream/white full-bleed
 * bands, two-tone headings with accent underline strokes, and framer-motion
 * scroll reveals. Reuses the shared landing primitives (Section, SectionLabel,
 * CTAButton, Reveal, Logo) and the EnvPathsDiagram for the Docker section.
 */
export default function LandingPage() {
  return (
    <div className="w-full">
      <Hero />
      <BuiltWith />
      <PoweredBy />
      <HowItWorks />
      <EnvironmentAndDocker />
      <Footer />
    </div>
  );
}

/** Two-tone accented word with the underline stroke used across headings. */
function Accent({ children }: { children: ReactNode }) {
  return (
    <span className="relative whitespace-nowrap text-accent-text">
      {children}
      <span
        className="absolute -bottom-1 left-0 h-1.5 w-full rounded-full bg-accent/60"
        aria-hidden
      />
    </span>
  );
}

/* ---------------------------------------------------------------- 1. HERO --- */

function Hero() {
  return (
    <Section tone="cream" className="pt-0" padY="pb-16 pt-4 sm:pb-24 sm:pt-6">
      <Reveal>
        <Logo
          imgClassName="h-96 w-auto sm:h-140"
          markClassName="h-14 w-14 text-2xl"
          wordClassName="text-4xl"
        />
        <div className="mt-4">
          <SectionLabel>Computational Pathology</SectionLabel>
        </div>
        <h1 className="mt-4 max-w-4xl text-5xl font-extrabold leading-[1.05] tracking-tight text-ink sm:text-6xl">
          Computational pathology, <Accent>orchestrated.</Accent>
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-muted">
          Bagheera is a browser GUI for the{' '}
          <span className="font-semibold text-ink">TRIDENT</span> (feature extraction) and{' '}
          <span className="font-semibold text-ink">PANTHER</span> (prototype training)
          computational-pathology pipelines. A single-GPU control room that takes you from
          raw whole-slide images to trained models and inference, no notebooks required.
        </p>
        <div className="mt-7 flex flex-wrap items-center gap-4">
          <CTAButton to="/start">Let&apos;s Start</CTAButton>
          <CTAButton to="/models" variant="outline">
            Browse Models
          </CTAButton>
        </div>
      </Reveal>
    </Section>
  );
}

/* ---------------------------------------------------------- 2. BUILT WITH --- */

interface Tech {
  icon: IconType;
  label: string;
}

const TECH: Tech[] = [
  { icon: SiReact, label: 'React' },
  { icon: SiFastapi, label: 'FastAPI' },
  { icon: SiPython, label: 'Python' },
  { icon: SiDocker, label: 'Docker' },
  { icon: SiSqlite, label: 'SQLite' },
  { icon: SiVite, label: 'Vite' },
  { icon: SiTailwindcss, label: 'Tailwind' },
];

function BuiltWith() {
  return (
    <Section tone="white" id="built-with" className="scroll-mt-24">
      <Reveal>
        <SectionLabel>Built With</SectionLabel>
        <h2 className="mt-6 max-w-3xl text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
          A deliberately <Accent>lean</Accent> stack.
        </h2>
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-ink-muted">
          No heavy frameworks: just a fast frontend, a typed Python API, and the two
          pipelines it orchestrates.
        </p>

        <div className="mt-12 flex flex-wrap items-center gap-x-10 gap-y-8">
          {TECH.map(({ icon: Icon, label }) => (
            <div
              key={label}
              className="group flex flex-col items-center gap-2 text-ink-faint transition-colors duration-200 hover:text-accent-text"
              title={label}
            >
              <Icon className="h-9 w-9 grayscale transition-all duration-200 group-hover:grayscale-0" />
              <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
            </div>
          ))}

          {/* Pipeline text badges — no official icons */}
          <PipelineBadge label="TRIDENT" />
          <PipelineBadge label="PANTHER" />
        </div>
      </Reveal>
    </Section>
  );
}

function PipelineBadge({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-2">
      <span className="rounded-lg border border-border bg-surface-subtle px-3.5 py-2 font-mono text-sm font-bold tracking-tight text-ink-muted transition-colors duration-200 hover:border-accent hover:text-accent-text">
        {label}
      </span>
      <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
        pipeline
      </span>
    </div>
  );
}

/* ---------------------------------------------------------- 3. POWERED BY --- */

function PoweredBy() {
  return (
    <Section tone="cream" id="powered-by" className="scroll-mt-24">
      <Reveal>
        <SectionLabel>Powered By</SectionLabel>
        <div className="mt-8 flex flex-col gap-8 lg:flex-row lg:items-center lg:gap-14">
          <HarvardMark />
          <p className="max-w-2xl text-lg leading-relaxed text-ink-muted">
            The PANTHER prototype model originates from the{' '}
            <span className="font-semibold text-ink">Mahmood Lab</span> at Harvard. Bagheera
            is an independent orchestration layer around the published TRIDENT and PANTHER
            pipelines. All credit for the underlying models belongs to their original
            authors.
          </p>
        </div>
      </Reveal>
    </Section>
  );
}

/** Mahmood Lab + Harvard Medical School logos, with text fallbacks if absent. */
function HarvardMark() {
  return (
    <div className="flex shrink-0 flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
      <LogoCard
        src="/mahmood_logo.png"
        alt="Mahmood Lab, AI for Pathology"
        title="Mahmood Lab"
        subtitle="AI for Pathology"
      />
      <LogoCard
        src="/harvard_logo.png"
        alt="Harvard Medical School"
        title="Harvard"
        subtitle="Medical School"
      />
    </div>
  );
}

function LogoCard({
  src,
  alt,
  title,
  subtitle,
}: {
  src: string;
  alt: string;
  title: string;
  subtitle: string;
}) {
  const [ok, setOk] = useState(true);
  return (
    <div className="grid h-20 place-items-center rounded-xl border border-border bg-surface px-6 shadow-card">
      {ok ? (
        <img src={src} alt={alt} className="max-h-12 w-auto" onError={() => setOk(false)} />
      ) : (
        <div className="text-center">
          <div className="text-base font-extrabold tracking-tight text-ink">{title}</div>
          <div className="text-xs font-medium text-ink-muted">{subtitle}</div>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------- 4. HOW IT WORKS --- */

interface Step {
  icon: IconType;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    icon: FiCpu,
    title: 'TRIDENT: extract features',
    body: 'Run feature extraction over your whole-slide images to produce per-slide .h5 feature files.',
  },
  {
    icon: FiScissors,
    title: 'Create a K-fold split',
    body: 'Turn your manifest CSV into a reproducible K-fold split for cross-validated training.',
  },
  {
    icon: FiLayers,
    title: 'PANTHER: train prototypes',
    body: 'Train prototype models on the extracted features across every fold of the split.',
  },
  {
    icon: FiPlay,
    title: 'Browse models & run inference',
    body: 'Inspect each fold, review visualizations, and run the trained model on new slides.',
  },
];

function HowItWorks() {
  return (
    <Section tone="white" id="how-it-works" className="scroll-mt-24">
      <Reveal>
        <SectionLabel>How It Works</SectionLabel>
        <h2 className="mt-6 max-w-3xl text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
          From raw slides to <Accent>inference</Accent>, step by step.
        </h2>
      </Reveal>

      <ol className="mt-12 space-y-4">
        {STEPS.map((step, i) => (
          <Reveal key={step.title} delay={i * 0.06}>
            <StepRow index={i + 1} step={step} />
          </Reveal>
        ))}
      </ol>

      <Reveal delay={0.1}>
        <div className="mt-12">
          <CTAButton to="/start">Let&apos;s Start</CTAButton>
        </div>
      </Reveal>
    </Section>
  );
}

function StepRow({ index, step }: { index: number; step: Step }) {
  const { icon: Icon, title, body } = step;
  return (
    <li className="flex items-start gap-5 rounded-xl border border-border bg-surface p-6 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-border-strong hover:shadow-card-hover">
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent text-base font-black text-ink shadow-glow">
        {index}
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <Icon className="h-5 w-5 shrink-0 text-accent-text" aria-hidden />
          <h3 className="text-lg font-bold tracking-tight text-ink">{title}</h3>
        </div>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{body}</p>
      </div>
    </li>
  );
}

/* ----------------------------------------------- 5. ENVIRONMENT & DOCKER --- */

function EnvironmentAndDocker() {
  return (
    <Section tone="cream" id="deployment" className="scroll-mt-24">
      <Reveal>
        <SectionLabel>Data &amp; Docker</SectionLabel>
        <h2 className="mt-6 max-w-3xl text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
          You set just <Accent>three folders.</Accent>
        </h2>
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-ink-muted">
          Bagheera runs inside <span className="font-semibold text-ink">Docker</span> so it works
          the same on any machine. Your files stay on your computer. You just point Docker at them
          with <span className="font-semibold text-ink">three settings</span> in your{' '}
          <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-sm text-ink">.env</code>:
          where your slides come <span className="font-semibold text-ink">in</span>, and where your
          results go <span className="font-semibold text-ink">out</span>.
        </p>
      </Reveal>
      <EnvPathsDiagram />
    </Section>
  );
}

/* -------------------------------------------------------------- 6. FOOTER --- */

function Footer() {
  return (
    <footer className="w-full border-t border-border bg-surface">
      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-12 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex flex-col gap-3">
          <Logo variant="horizontal" wordClassName="text-lg" markClassName="h-8 w-8 text-sm" />
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub repository"
            className="inline-flex w-fit items-center gap-2 rounded-full border border-border bg-surface px-4 py-2 text-sm font-semibold text-ink-muted transition-colors hover:border-accent hover:text-accent-text"
          >
            <FaGithub className="h-4 w-4" />
            GitHub
          </a>
        </div>

        <div className="flex flex-col gap-3">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-ink-faint">
            Built by
          </span>
          <ul className="flex flex-col gap-2">
            {TEAM.map((p) => (
              <li key={p.url}>
                <a
                  href={p.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 text-sm font-medium text-ink-muted transition-colors hover:text-accent-text"
                >
                  <FaLinkedin className="h-4 w-4 shrink-0 text-accent-text" />
                  {p.name}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}
