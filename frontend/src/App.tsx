import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom';
import TridentTrainingPage from './pages/TridentTrainingPage';
import PantherTrainingPage from './pages/PantherTrainingPage';
import ModelsBrowserPage from './pages/ModelsBrowserPage';
import GroupDetailPage from './pages/GroupDetailPage';
import InferencePage from './pages/InferencePage';
import QueuePage from './pages/QueuePage';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg text-ink">
        <header className="sticky top-0 z-30 border-b border-border/70 bg-surface/80 backdrop-blur-lg">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
            <div className="flex items-center gap-2.5">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-grad-brand text-sm font-black text-white shadow-glow">
                B
              </span>
              <h1 className="bg-grad-brand bg-clip-text text-lg font-extrabold tracking-tight text-transparent">
                Bagheera
              </h1>
            </div>
            <nav className="flex items-center gap-1 rounded-full border border-border bg-surface/70 p-1 text-sm shadow-sm">
              <TopLink to="/training/trident" label="TRIDENT" />
              <TopLink to="/training/panther" label="PANTHER" />
              <span className="mx-1 h-4 w-px bg-border-strong" aria-hidden />
              <TopLink to="/models" label="Models" />
              <TopLink to="/queue" label="Queue" />
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-10">
          <Routes>
            <Route path="/" element={<Navigate to="/training/trident" replace />} />
            <Route path="/training" element={<Navigate to="/training/trident" replace />} />
            <Route path="/training/trident" element={<TridentTrainingPage />} />
            <Route path="/training/panther" element={<PantherTrainingPage />} />
            <Route path="/models" element={<ModelsBrowserPage />} />
            <Route path="/models/:groupId" element={<GroupDetailPage />} />
            <Route path="/models/:modelId/inference" element={<InferencePage />} />
            <Route path="/queue" element={<QueuePage />} />
            <Route path="*" element={<Navigate to="/training/trident" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

function TopLink({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded-full px-3.5 py-1.5 text-sm font-semibold transition-all duration-150 ${
          isActive
            ? 'bg-grad-accent text-white shadow-glow'
            : 'text-ink-muted hover:bg-surface-subtle hover:text-ink'
        }`
      }
    >
      {label}
    </NavLink>
  );
}
