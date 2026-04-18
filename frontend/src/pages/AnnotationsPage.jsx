import { useCallback, useEffect, useState } from "react";
import { createAnnotation, deleteAnnotation, listAnnotations } from "../api/annotations.js";
import Toast from "../components/Toast.jsx";

function relativeTime(isoString) {
  const delta = Math.floor((Date.now() - new Date(isoString)) / 1000);
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

const TYPE_BADGE = {
  slide: "bg-panther-400/10 text-panther-700 border border-panther-400/30",
  cluster: "bg-accent-light text-accent border border-accent/30",
};

export default function AnnotationsPage() {
  const [targetId, setTargetId] = useState("");
  const [targetType, setTargetType] = useState("slide");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState({ message: "", kind: "info" });

  const [annotations, setAnnotations] = useState([]);
  const [filterTargetId, setFilterTargetId] = useState("");
  const [filterTargetType, setFilterTargetType] = useState("all");

  const fetchAnnotations = useCallback(async () => {
    try {
      const data = await listAnnotations({
        targetId: filterTargetId || undefined,
        targetType: filterTargetType !== "all" ? filterTargetType : undefined,
      });
      setAnnotations(data);
    } catch {
      // silently ignore fetch errors in the feed
    }
  }, [filterTargetId, filterTargetType]);

  useEffect(() => {
    fetchAnnotations();
  }, [fetchAnnotations]);

  async function onSubmit(e) {
    e.preventDefault();
    if (!targetId.trim() || !note.trim()) {
      setToast({ message: "Target ID and note are required", kind: "error" });
      return;
    }
    setSubmitting(true);
    try {
      const res = await createAnnotation({
        target_id: targetId.trim(),
        target_type: targetType,
        note: note.trim(),
      });
      setToast({ message: `Saved annotation ${res.annotation_id.slice(0, 8)}…`, kind: "success" });
      setNote("");
      fetchAnnotations();
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      setToast({ message: `Save failed: ${detail}`, kind: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  async function onDelete(annotationId) {
    try {
      await deleteAnnotation(annotationId);
      setAnnotations((prev) => prev.filter((a) => a.annotation_id !== annotationId));
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      setToast({ message: `Delete failed: ${detail}`, kind: "error" });
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl text-panther-900">Annotations</h1>

      <div className="grid md:grid-cols-2 gap-8 items-start">
        {/* Left: create form */}
        <form
          onSubmit={onSubmit}
          className="bg-white border border-panther-400/20 rounded-xl p-6 shadow-sm space-y-4"
        >
          <h2 className="font-display text-lg text-panther-800">New annotation</h2>

          <div>
            <label className="block text-sm font-medium text-panther-700 mb-1">Target ID</label>
            <input
              type="text"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              placeholder="slide id or cluster id"
              className="w-full border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-panther-700 mb-1">Target type</label>
            <select
              value={targetType}
              onChange={(e) => setTargetType(e.target.value)}
              className="border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
            >
              <option value="slide">slide</option>
              <option value="cluster">cluster</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-panther-700 mb-1">Note</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={5}
              placeholder="High grade dysplasia…"
              className="w-full border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none resize-none"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="bg-accent hover:bg-accent-hover text-white font-body font-medium px-5 py-2.5 rounded-lg transition-colors disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Save annotation"}
          </button>
        </form>

        {/* Right: annotation feed */}
        <div className="space-y-4">
          {/* Filter bar */}
          <div className="flex gap-3 flex-wrap">
            <input
              type="text"
              value={filterTargetId}
              onChange={(e) => setFilterTargetId(e.target.value)}
              placeholder="Filter by target ID…"
              className="flex-1 min-w-0 border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
            />
            <select
              value={filterTargetType}
              onChange={(e) => setFilterTargetType(e.target.value)}
              className="border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
            >
              <option value="all">All types</option>
              <option value="slide">slide</option>
              <option value="cluster">cluster</option>
            </select>
          </div>

          {/* Feed */}
          {annotations.length === 0 ? (
            <p className="text-panther-400 text-sm italic">No annotations yet.</p>
          ) : (
            <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
              {annotations.map((a) => (
                <div
                  key={a.annotation_id}
                  className="bg-white border border-panther-400/20 rounded-xl p-4 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-md text-xs font-medium ${TYPE_BADGE[a.target_type] ?? TYPE_BADGE.slide}`}
                      >
                        {a.target_type}
                      </span>
                      <span className="font-mono text-xs text-panther-500 truncate max-w-[200px]">
                        {a.target_id}
                      </span>
                    </div>
                    <button
                      onClick={() => onDelete(a.annotation_id)}
                      aria-label="Delete annotation"
                      className="text-panther-400 hover:text-accent transition-colors flex-shrink-0"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        className="w-4 h-4"
                      >
                        <path
                          fillRule="evenodd"
                          d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </button>
                  </div>
                  <p className="text-sm text-panther-800 whitespace-pre-wrap">{a.note}</p>
                  <p className="text-xs text-panther-400 mt-2">{relativeTime(a.created_at)}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Toast
        message={toast.message}
        kind={toast.kind}
        onClose={() => setToast({ message: "", kind: "info" })}
      />
    </div>
  );
}
