import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }) =>
  `px-3 py-2 rounded-md text-sm font-medium transition ${
    isActive ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-200"
  }`;

export default function NavBar() {
  return (
    <header className="bg-white border-b border-slate-200">
      <nav className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-4">
        <span className="text-lg font-bold text-slate-900">Bagheera</span>
        <span className="text-xs text-slate-500">PANTHER GUI · Sheba</span>
        <div className="flex-1" />
        <NavLink to="/inference" className={linkClass}>
          Inference
        </NavLink>
        <NavLink to="/jobs" className={linkClass}>
          Jobs
        </NavLink>
        <NavLink to="/annotations" className={linkClass}>
          Annotations
        </NavLink>
      </nav>
    </header>
  );
}
