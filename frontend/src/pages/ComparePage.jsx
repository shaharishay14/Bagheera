import { useEffect, useState } from "react";
import { createAnnotation } from "../api/annotations.js";
import { getVisualization, listJobs } from "../api/jobs.js";
import StatusBadge from "../components/StatusBadge.jsx";
import Toast from "../components/Toast.jsx";

function relativeTime(isoString) {
  if (!isoString) return "—";
  const delta = Math.floor((Date.now() - new Date(isoString)) / 1000);
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

function duration(startedAt, finishedAt) {
  if (!startedAt || !finishedAt) return "—";
  const secs = Math.round((new Date(finishedAt) - new Date(startedAt)) / 1000);
  return `${secs}s`;
}

function ClusterCard({ cluster }) {
  return (
    <div className="bg-white border border-panther-400/20 rounded-xl p-3 shadow-sm">
      <div className="flex items-center justify-between mb-1">
        <span className="font-mono text-xs text-panther-500">#{cluster.prototype_index}</span>
        {cluster.label && (
          <span className="text-xs text-panther-700 font-medium">{cluster.label}</span>
        )}
      </div>
      <ul className="space-y-0.5">
        {cluster.patches.map((p) => (
          <li key={p} className="font-mono text-xs text-panther-400 truncate">
            {p}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MetricsStrip({ viz }) {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-panther-600 font-mono bg-panther-50 border border-panther-400/20 rounded-lg px-4 py-2">
      <span>C=<strong className="text-panther-900">{viz.num_clusters}</strong></span>
      <span>encoder=<strong className="text-panther-900">{viz.encoder}</strong></span>
      <span>τ=<strong className="text-panther-900">{viz.tau.toFixed(2)}</strong></span>
      <span>EM=<strong className="text-panther-900">{viz.em_iter}</strong></span>
      <span>out=<strong className="text-panther-900">{viz.out_type}</strong></span>
      <span>dur=<strong className="text-panther-900">{duration(viz.started_at, viz.finished_at)}</strong></span>
    </div>
  );
}

function JobPanel({ label, doneJobs, selectedJobId, onSelect, viz }) {
  const gridCols = viz && viz.num_clusters > 8 ? "grid-cols-4" : "grid-cols-2";

  return (
    <div className="flex-1 min-w-0 space-y-4">
      <div className="flex items-center gap-2">
        <span className="font-body font-medium text-panther-600 uppercase tracking-widest text-xs">
          {label}
        </span>
      </div>
      <select
        value={selectedJobId}
        onChange={(e) => onSelect(e.target.value)}
        className="w-full border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none bg-white"
      >
        <option value="">— select a completed job —</option>
        {doneJobs.map((j) => (
          <option key={j.id} value={j.id}>
            {j.dataset_id} · C={j.num_clusters} · {j.encoder} · {relativeTime(j.finished_at)}
          </option>
        ))}
      </select>

      {viz ? (
        <div className="space-y-3">
          <MetricsStrip viz={viz} />
          <div className={`grid ${gridCols} gap-3`}>
            {viz.clusters.map((c) => (
              <ClusterCard key={c.cluster_id} cluster={c} />
            ))}
          </div>
        </div>
      ) : (
        selectedJobId && (
          <p className="text-panther-400 text-sm italic">Loading…</p>
        )
      )}
    </div>
  );
}

export default function ComparePage() {
  const [doneJobs, setDoneJobs] = useState([]);
  const [leftJobId, setLeftJobId] = useState("");
  const [rightJobId, setRightJobId] = useState("");
  const [leftViz, setLeftViz] = useState(null);
  const [rightViz, setRightViz] = useState(null);

  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState({ message: "", kind: "info" });

  useEffect(() => {
    listJobs()
      .then((jobs) => setDoneJobs(jobs.filter((j) => j.status === "Done")))
      .catch(() => {});
  }, []);

  function handleSelectLeft(jobId) {
    setLeftJobId(jobId);
    setLeftViz(null);
    if (jobId) getVisualization(jobId).then(setLeftViz).catch(() => {});
  }

  function handleSelectRight(jobId) {
    setRightJobId(jobId);
    setRightViz(null);
    if (jobId) getVisualization(jobId).then(setRightViz).catch(() => {});
  }

  const comparisonTargetId =
    leftJobId && rightJobId ? `${leftJobId} vs ${rightJobId}` : "";

  async function onSaveNote(e) {
    e.preventDefault();
    if (!note.trim() || !comparisonTargetId) {
      setToast({ message: "Select two jobs and write a note first", kind: "error" });
      return;
    }
    setSaving(true);
    try {
      const res = await createAnnotation({
        target_id: comparisonTargetId,
        target_type: "slide",
        note: note.trim(),
      });
      setToast({
        message: `Comparison note ${res.annotation_id.slice(0, 8)}… saved`,
        kind: "success",
      });
      setNote("");
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      setToast({ message: `Save failed: ${detail}`, kind: "error" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <h1 className="font-display text-3xl text-panther-900">Compare runs</h1>

      {doneJobs.length === 0 && (
        <p className="text-panther-400 text-sm italic">
          No completed jobs yet — run some inferences first.
        </p>
      )}

      {/* Side-by-side panels */}
      <div className="flex flex-col md:flex-row gap-0 items-stretch">
        <JobPanel
          label="Run A"
          doneJobs={doneJobs}
          selectedJobId={leftJobId}
          onSelect={handleSelectLeft}
          viz={leftViz}
        />

        {/* VS divider */}
        <div className="flex flex-col items-center justify-start pt-8 px-6 shrink-0">
          <div className="hidden md:flex flex-col items-center gap-2">
            <div className="w-px flex-1 bg-panther-400/20 min-h-[2rem]" />
            <span className="font-display text-lg text-panther-400 select-none">VS</span>
            <div className="w-px flex-1 bg-panther-400/20 min-h-[2rem]" />
          </div>
          <span className="md:hidden font-display text-lg text-panther-400 my-4">VS</span>
        </div>

        <JobPanel
          label="Run B"
          doneJobs={doneJobs}
          selectedJobId={rightJobId}
          onSelect={handleSelectRight}
          viz={rightViz}
        />
      </div>

      {/* Comparison annotation form */}
      <div className="border-t border-panther-400/20 pt-6">
        <h2 className="font-display text-xl text-panther-800 mb-4">Add comparison note</h2>
        <form
          onSubmit={onSaveNote}
          className="bg-white border border-panther-400/20 rounded-xl p-6 shadow-sm space-y-4"
        >
          <div>
            <label className="block text-sm font-medium text-panther-700 mb-1">Target</label>
            <input
              type="text"
              readOnly
              value={comparisonTargetId || "Select both jobs above"}
              className="w-full border border-panther-400/20 rounded-lg px-3 py-2 font-mono text-sm bg-panther-50 text-panther-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-panther-700 mb-1">Note</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={4}
              placeholder="C=10 outperforms C=14 because…"
              className="w-full border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none resize-none"
            />
          </div>
          <button
            type="submit"
            disabled={saving || !comparisonTargetId}
            className="bg-accent hover:bg-accent-hover text-white font-body font-medium px-5 py-2.5 rounded-lg transition-colors disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save note"}
          </button>
        </form>
      </div>

      <Toast
        message={toast.message}
        kind={toast.kind}
        onClose={() => setToast({ message: "", kind: "info" })}
      />
    </div>
  );
}
