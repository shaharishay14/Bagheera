import { Routes, Route, Navigate } from "react-router-dom";
import NavBar from "./components/NavBar.jsx";
import InferencePage from "./pages/InferencePage.jsx";
import JobsDashboard from "./pages/JobsDashboard.jsx";
import AnnotationsPage from "./pages/AnnotationsPage.jsx";
import ComparePage from "./pages/ComparePage.jsx";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <NavBar />
      <main className="flex-1 max-w-5xl w-full mx-auto p-6">
        <Routes>
          <Route path="/" element={<Navigate to="/inference" replace />} />
          <Route path="/inference" element={<InferencePage />} />
          <Route path="/jobs" element={<JobsDashboard />} />
          <Route path="/annotations" element={<AnnotationsPage />} />
          <Route path="/compare" element={<ComparePage />} />
        </Routes>
      </main>
    </div>
  );
}
