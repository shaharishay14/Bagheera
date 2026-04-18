const COLORS = {
  Queued: "bg-panther-400/10 text-panther-700 border border-panther-400/30",
  Processing: "bg-amber-50 text-amber-800 border border-amber-300",
  Done: "bg-emerald-50 text-emerald-800 border border-emerald-300",
  Error: "bg-accent-light text-accent border border-accent/30",
};

export default function StatusBadge({ status }) {
  const cls = COLORS[status] || COLORS.Queued;
  return (
    <span className={`inline-block px-2 py-1 rounded-md text-xs font-semibold ${cls}`}>
      {status}
    </span>
  );
}
