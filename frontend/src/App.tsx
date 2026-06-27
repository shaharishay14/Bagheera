import { useEffect, useState } from 'react';
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';
import { FaGithub } from 'react-icons/fa6';
import { FiGrid } from 'react-icons/fi';
import LandingPage from './pages/LandingPage';
import StartPage from './pages/StartPage';
import TridentTrainingPage from './pages/TridentTrainingPage';
import PantherTrainingPage from './pages/PantherTrainingPage';
import ModelsBrowserPage from './pages/ModelsBrowserPage';
import GroupDetailPage from './pages/GroupDetailPage';
import InferencePage from './pages/InferencePage';
import QueuePage from './pages/QueuePage';

const GITHUB_URL = 'https://github.com/shaharishay14/Bagheera';

/** Landing-page section anchors (in-page scroll links). */
const LANDING_SECTIONS = [
  { href: '#how-it-works', label: 'How it works' },
  { href: '#built-with', label: 'Tech stack' },
  { href: '#powered-by', label: 'Powered by' },
  { href: '#deployment', label: 'Data & Docker' },
];

/** Functional ("app mode") nav links shown after the user clicks Let's Start. */
const APP_LINKS = [
  { to: '/training/trident', label: 'TRIDENT' },
  { to: '/training/panther', label: 'PANTHER' },
  { to: '/models', label: 'Models' },
  { to: '/queue', label: 'Queue' },
];

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg text-ink">
        <ScrollToHash />
        <Header />
        <Routes>
          {/* Full-bleed routes control their own width */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/start" element={<StartPage />} />
          {/* Functional routes share the centered container */}
          <Route element={<AppShell />}>
            <Route path="/training" element={<Navigate to="/training/trident" replace />} />
            <Route path="/training/trident" element={<TridentTrainingPage />} />
            <Route path="/training/panther" element={<PantherTrainingPage />} />
            <Route path="/models" element={<ModelsBrowserPage />} />
            <Route path="/models/:groupId" element={<GroupDetailPage />} />
            <Route path="/models/:modelId/inference" element={<InferencePage />} />
            <Route path="/queue" element={<QueuePage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

/**
 * Scrolls to the element matching the URL hash (e.g. /#deployment) after navigation.
 * Needed because this is an SPA — on a fresh deep-link the target section isn't
 * in the DOM yet when the browser tries to resolve the hash, so the native jump
 * is missed. Runs on every location change with a short delay for render.
 */
function ScrollToHash() {
  const { hash, pathname } = useLocation();

  useEffect(() => {
    if (!hash) {
      window.scrollTo({ top: 0 });
      return;
    }
    const id = hash.slice(1);
    const t = window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    }, 80);
    return () => window.clearTimeout(t);
  }, [hash, pathname]);

  return null;
}

/** Centered container layout for the functional (non-landing) pages. */
function AppShell() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <Outlet />
    </main>
  );
}

/**
 * Floating, veto-style navbar. At the top of the page it sits flush and
 * transparent; once the user scrolls past ~20px it detaches into a centered
 * rounded pill with a shadow and border. Sticky + in-flow so functional pages
 * keep their natural top spacing (no fixed overlay, no layout shift).
 *
 * The nav is context-aware: on the landing page (`/`) it links to the on-page
 * sections and shows the "Let's Start" CTA. Once the user has started (the
 * `/start` selection page and every functional page) it switches to the app
 * links (TRIDENT/PANTHER/Models/Queue) plus an "Options" link back to the
 * four-card selection. In both modes the logo returns to the landing page.
 */
function Header() {
  const [scrolled, setScrolled] = useState(false);
  const [logoOk, setLogoOk] = useState(true);
  const { pathname } = useLocation();
  const isLanding = pathname === '/';

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className="sticky top-0 z-40">
      <div
        className={`mx-auto flex max-w-6xl items-center justify-between px-5 transition-all duration-300 ease-out ${
          scrolled
            ? 'mt-3 rounded-full border border-border bg-surface/90 py-2 shadow-card backdrop-blur-lg'
            : 'mt-0 border border-transparent bg-bg/50 py-3.5 backdrop-blur-sm'
        }`}
      >
        <Link
          to="/"
          className="flex items-center gap-2.5"
          aria-label="Bagheera home"
          onClick={() => {
            if (isLanding) window.scrollTo({ top: 0, behavior: 'smooth' });
          }}
        >
          {logoOk ? (
            <>
              {/* The brand asset is a stacked lockup (panther over wordmark);
                  crop to just the shield for a crisp horizontal navbar mark. */}
              <span className="flex h-9 w-10 items-start justify-center overflow-hidden">
                <img
                  src="/bagheera_logo.png"
                  alt=""
                  aria-hidden
                  className="h-[3.4rem] w-auto max-w-none"
                  onError={() => setLogoOk(false)}
                />
              </span>
              <span className="text-lg font-extrabold tracking-tight text-ink">
                Bagheera
              </span>
            </>
          ) : (
            <>
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-grad-brand text-sm font-black text-white shadow-glow">
                B
              </span>
              <span className="text-lg font-extrabold tracking-tight text-ink">
                Bagheera
              </span>
            </>
          )}
        </Link>

        {isLanding ? <LandingNav /> : <AppNav />}
      </div>
    </header>
  );
}

/** Landing-mode nav: in-page section anchors + GitHub + the Let's Start CTA. */
function LandingNav() {
  return (
    <nav className="flex items-center gap-1 text-sm">
      {LANDING_SECTIONS.map((s) => (
        <a
          key={s.href}
          href={s.href}
          className="hidden rounded-full px-3.5 py-1.5 text-sm font-semibold text-ink-muted transition-all duration-150 hover:bg-surface-subtle hover:text-ink sm:inline-block"
        >
          {s.label}
        </a>
      ))}
      <GitHubIconLink />
      <Link
        to="/start"
        className="ml-1.5 inline-flex items-center rounded-full bg-accent px-4 py-2 text-sm font-semibold text-ink shadow-glow transition-all duration-150 hover:-translate-y-0.5 hover:bg-accent-dark hover:shadow-glow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
      >
        Let&apos;s Start
      </Link>
    </nav>
  );
}

/** App-mode nav: an Options link back to the four-card page + the pipeline links. */
function AppNav() {
  return (
    <nav className="flex items-center gap-1 text-sm">
      <NavLink
        to="/start"
        end
        className={({ isActive }) =>
          `inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition-all duration-150 ${
            isActive
              ? 'bg-accent-muted text-accent-text'
              : 'text-ink-muted hover:bg-surface-subtle hover:text-ink'
          }`
        }
      >
        <FiGrid className="h-4 w-4" aria-hidden />
        <span className="hidden sm:inline">Options</span>
      </NavLink>
      <span className="mx-1 h-4 w-px bg-border-strong" aria-hidden />
      {APP_LINKS.map((l) => (
        <TopLink key={l.to} to={l.to} label={l.label} />
      ))}
      <GitHubIconLink />
    </nav>
  );
}

function GitHubIconLink() {
  return (
    <a
      href={GITHUB_URL}
      target="_blank"
      rel="noreferrer"
      aria-label="GitHub repository"
      className="ml-1 grid h-9 w-9 place-items-center rounded-full text-ink-muted transition-colors hover:bg-surface-subtle hover:text-ink"
    >
      <FaGithub className="h-4 w-4" />
    </a>
  );
}

function TopLink({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `hidden rounded-full px-3.5 py-1.5 text-sm font-semibold transition-all duration-150 sm:inline-block ${
          isActive
            ? 'bg-accent-muted text-accent-text'
            : 'text-ink-muted hover:bg-surface-subtle hover:text-ink'
        }`
      }
    >
      {label}
    </NavLink>
  );
}
