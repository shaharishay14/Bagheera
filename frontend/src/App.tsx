import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom';
import TridentTrainingPage from './pages/TridentTrainingPage';
import PantherTrainingPage from './pages/PantherTrainingPage';
import ModelsBrowserPage from './pages/ModelsBrowserPage';
import GroupDetailPage from './pages/GroupDetailPage';
import InferencePage from './pages/InferencePage';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50 text-slate-900">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <h1 className="text-lg font-semibold tracking-tight">Bagheera</h1>
            <nav className="flex items-center gap-1 text-sm">
              <span className="mr-2 text-slate-400">Training</span>
              <TopLink to="/training/trident" label="TRIDENT" />
              <TopLink to="/training/panther" label="PANTHER" />
              <span className="mx-2 text-slate-300">|</span>
              <TopLink to="/models" label="Models" />
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
        `rounded-md px-3 py-1.5 text-sm font-medium ${
          isActive
            ? 'bg-slate-900 text-white'
            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
        }`
      }
    >
      {label}
    </NavLink>
  );
}
