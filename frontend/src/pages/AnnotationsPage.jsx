import { useState } from "react";
import { createAnnotation } from "../api/annotations.js";
import Toast from "../components/Toast.jsx";

export default function AnnotationsPage() {
  const [targetId, setTargetId] = useState("");
  const [targetType, setTargetType] = useState("slide");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState({ message: "", kind: "info" });

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
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      setToast({ message: `Save failed: ${detail}`, kind: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Annotations</h1>
      <form onSubmit={onSubmit} className="bg-white border rounded p-6 space-y-4 max-w-xl">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Target ID</label>
          <input
            type="text"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            placeholder="slide id or cluster id"
            className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Target type</label>
          <select
            value={targetType}
            onChange={(e) => setTargetType(e.target.value)}
            className="w-40 px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <option value="slide">slide</option>
            <option value="cluster">cluster</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Note</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={5}
            placeholder="High grade dysplasia…"
            className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 bg-slate-900 text-white rounded hover:bg-slate-700 disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Save annotation"}
        </button>
      </form>
      <Toast
        message={toast.message}
        kind={toast.kind}
        onClose={() => setToast({ message: "", kind: "info" })}
      />
    </div>
  );
}
