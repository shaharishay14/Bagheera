import type { IconType } from 'react-icons';
import { Link } from 'react-router-dom';
import { FaMicroscope, FaBrain, FaLayerGroup, FaListCheck } from 'react-icons/fa6';
import SectionLabel from '../components/landing/SectionLabel';

interface Option {
  to: string;
  icon: IconType;
  title: string;
  description: string;
  when: string;
}

const OPTIONS: Option[] = [
  {
    to: '/training/trident',
    icon: FaMicroscope,
    title: 'TRIDENT',
    description: 'Extract features from whole-slide images.',
    when: 'Start here with raw WSIs.',
  },
  {
    to: '/training/panther',
    icon: FaBrain,
    title: 'PANTHER',
    description: 'Train prototype models on extracted features.',
    when: 'After TRIDENT features exist.',
  },
  {
    to: '/models',
    icon: FaLayerGroup,
    title: 'Models',
    description: 'Browse, inspect, and manage trained models.',
    when: 'To review or run inference.',
  },
  {
    to: '/queue',
    icon: FaListCheck,
    title: 'Queue',
    description: 'Monitor running and queued jobs.',
    when: 'To track progress.',
  },
];

export default function StartPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 pb-24 pt-28 sm:pt-36">
      <SectionLabel>Get Started</SectionLabel>
      <h1 className="mt-6 max-w-3xl text-4xl font-extrabold leading-tight tracking-tight text-ink sm:text-5xl">
        Where would you like to begin?
      </h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-muted">
        Pick a stage of the pipeline. Each step flows into the next, from raw slides to
        trained models and inference.
      </p>

      <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {OPTIONS.map((opt) => (
          <OptionCard key={opt.to} option={opt} />
        ))}
      </div>
    </main>
  );
}

function OptionCard({ option }: { option: Option }) {
  const { to, icon: Icon, title, description, when } = option;
  return (
    <Link
      to={to}
      className="group flex flex-col rounded-xl border border-border bg-surface p-6 shadow-card transition-all duration-200 hover:-translate-y-1 hover:border-border-strong hover:shadow-card-hover"
    >
      <span className="grid h-12 w-12 place-items-center rounded-lg bg-accent-muted text-accent-text transition-colors duration-200 group-hover:bg-accent group-hover:text-ink">
        <Icon className="h-6 w-6" />
      </span>
      <h2 className="mt-5 text-lg font-bold tracking-tight text-ink transition-colors duration-200 group-hover:text-accent-text">
        {title}
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">{description}</p>
      <p className="mt-auto pt-4 text-xs font-medium uppercase tracking-wide text-ink-faint">
        {when}
      </p>
    </Link>
  );
}
