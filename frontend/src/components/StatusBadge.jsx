const COLORS = {
  Queued: "bg-slate-200 text-slate-800",
  Processing: "bg-amber-200 text-amber-900",
  Done: "bg-emerald-200 text-emerald-900",
  Error: "bg-rose-200 text-rose-900",
};

export default function StatusBadge({ status }) {
  const cls = COLORS[status] || "bg-slate-200 text-slate-800";
  return (
    <span className={`inline-block px-2 py-1 rounded text-xs font-semibold ${cls}`}>
      {status}
    </span>
  );
}
