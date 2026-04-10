import { useState } from "react";
import { submitInference } from "../api/inference.js";
import Toast from "../components/Toast.jsx";

export default function InferencePage() {
  const [datasetId, setDatasetId] = useState("");
  const [numClusters, setNumClusters] = useState(5);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState({ message: "", kind: "info" });

  async function onSubmit(e) {
    e.preventDefault();
    if (!datasetId.trim()) {
      setToast({ message: "Dataset path is required", kind: "error" });
      return;
    }
    setSubmitting(true);
    try {
      const res = await submitInference({
        dataset_id: datasetId.trim(),
        num_clusters: Number(numClusters),
      });
      setToast({ message: `Job ${res.job_id.slice(0, 8)}… queued`, kind: "success" });
      setDatasetId("");
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      setToast({ message: `Submit failed: ${detail}`, kind: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Submit Inference</h1>
      <form onSubmit={onSubmit} className="bg-white border rounded p-6 space-y-4 max-w-xl">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Dataset path (TIFF)
          </label>
          <input
            type="text"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            placeholder="/data/slides/slide_001.tiff"
            className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Number of clusters (2–20)
          </label>
          <input
            type="number"
            min={2}
            max={20}
            value={numClusters}
            onChange={(e) => setNumClusters(e.target.value)}
            className="w-32 px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 bg-slate-900 text-white rounded hover:bg-slate-700 disabled:opacity-50"
        >
          {submitting ? "Submitting…" : "Submit Job"}
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
