import { NavLink } from "react-router-dom";
import logo from "../assets/bagheera-logo.svg";

const linkClass = ({ isActive }) =>
  `text-sm font-body transition-colors pb-0.5 ${
    isActive
      ? "text-white font-medium border-b-2 border-accent"
      : "text-panther-200 hover:text-white"
  }`;

export default function NavBar() {
  return (
    <header className="bg-panther-900 border-b border-panther-800">
      <nav className="max-w-5xl mx-auto px-6 flex items-center gap-6 h-14">
        <img src={logo} alt="Bagheera" className="h-7 w-auto" />
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
        <NavLink to="/compare" className={linkClass}>
          Compare
        </NavLink>
      </nav>
    </header>
  );
}
