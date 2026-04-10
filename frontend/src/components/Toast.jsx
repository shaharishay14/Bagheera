import { useEffect } from "react";

export default function Toast({ message, kind = "info", onClose, durationMs = 3000 }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onClose, durationMs);
    return () => clearTimeout(t);
  }, [message, durationMs, onClose]);

  if (!message) return null;

  const color =
    kind === "error"
      ? "bg-rose-600"
      : kind === "success"
      ? "bg-emerald-600"
      : "bg-slate-800";

  return (
    <div
      className={`fixed bottom-6 right-6 px-4 py-3 rounded shadow-lg text-white ${color}`}
      role="status"
    >
      {message}
    </div>
  );
}
