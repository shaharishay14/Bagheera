import { useEffect, useRef, useState } from "react";

const STYLES = {
  error: "bg-white border-l-4 border-accent text-panther-900",
  success: "bg-white border-l-4 border-emerald-500 text-panther-900",
  info: "bg-white border-l-4 border-panther-400 text-panther-900",
};

export default function Toast({ message, kind = "info", onClose, durationMs = 3000 }) {
  const timerRef = useRef(null);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (!message) return;
    if (paused) return;
    timerRef.current = setTimeout(onClose, durationMs);
    return () => clearTimeout(timerRef.current);
  }, [message, durationMs, onClose, paused]);

  if (!message) return null;

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg ${
        STYLES[kind] || STYLES.info
      }`}
      role="status"
      onMouseEnter={() => {
        setPaused(true);
        clearTimeout(timerRef.current);
      }}
      onMouseLeave={() => setPaused(false)}
    >
      <span className="text-sm">{message}</span>
      <button
        onClick={onClose}
        aria-label="Dismiss"
        className="ml-1 text-panther-400 hover:text-panther-700 text-lg leading-none transition-colors"
      >
        ×
      </button>
    </div>
  );
}
