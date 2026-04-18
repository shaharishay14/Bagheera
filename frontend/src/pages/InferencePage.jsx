import { useState } from "react";
import { submitInference } from "../api/inference.js";
import Toast from "../components/Toast.jsx";

export default function InferencePage() {
  const [datasetId, setDatasetId] = useState("");
  const [numClusters, setNumClusters] = useState(5);
  const [encoder, setEncoder] = useState("uni");
  const [emIter, setEmIter] = useState(1);
  const [tau, setTau] = useState(1.0);
  const [outType, setOutType] = useState("allcat");
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
        encoder,
        em_iter: Number(emIter),
        tau: Number(tau),
        out_type: outType,
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
      <div>
        <h1 className="font-display text-3xl text-panther-900">Submit inference</h1>
        <p className="text-panther-600 text-sm mt-1">
          Queue a PANTHER run against a local TIFF dataset.
        </p>
      </div>

      <form
        onSubmit={onSubmit}
        className="bg-white border border-panther-400/20 rounded-xl p-6 shadow-sm max-w-xl space-y-4"
      >
        <div>
          <label className="block text-sm font-medium text-panther-700 mb-1">
            Dataset path (TIFF)
          </label>
          <input
            type="text"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            placeholder="/data/slides/slide_001.tiff"
            className="w-full border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-panther-700 mb-1">
            Number of clusters (2–32)
          </label>
          <input
            type="number"
            min={2}
            max={32}
            value={numClusters}
            onChange={(e) => setNumClusters(e.target.value)}
            className="w-32 border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
          />
        </div>

        <details className="border border-panther-400/20 rounded-lg p-4">
          <summary className="font-body font-medium text-panther-700 cursor-pointer select-none">
            Advanced PANTHER parameters
          </summary>
          <div className="mt-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-panther-700 mb-1">Encoder</label>
              <select
                value={encoder}
                onChange={(e) => setEncoder(e.target.value)}
                className="border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
              >
                <option value="uni">uni</option>
                <option value="ctranspath">ctranspath</option>
                <option value="resnet50">resnet50</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-panther-700 mb-1">
                EM iterations (1–10)
              </label>
              <input
                type="number"
                min={1}
                max={10}
                value={emIter}
                onChange={(e) => setEmIter(e.target.value)}
                className="w-24 border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-panther-700 mb-1">
                Tau — <span className="font-mono text-sm text-panther-600">{Number(tau).toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={0.01}
                max={10}
                step={0.01}
                value={tau}
                onChange={(e) => setTau(e.target.value)}
                className="w-full accent-accent"
              />
              <div className="flex justify-between text-xs text-panther-400 mt-1">
                <span>0.01</span>
                <span>10.00</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-panther-700 mb-1">Output type</label>
              <select
                value={outType}
                onChange={(e) => setOutType(e.target.value)}
                className="border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40 focus:outline-none"
              >
                <option value="allcat">allcat</option>
                <option value="weight_avg_mean">weight_avg_mean</option>
                <option value="weight_avg_all">weight_avg_all</option>
              </select>
            </div>
          </div>
        </details>

        <button
          type="submit"
          disabled={submitting}
          className="bg-accent hover:bg-accent-hover text-white font-body font-medium px-5 py-2.5 rounded-lg transition-colors disabled:opacity-50"
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
