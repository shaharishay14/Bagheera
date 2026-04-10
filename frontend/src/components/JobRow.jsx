import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import StatusBadge from "./StatusBadge.jsx";

export default function JobRow({ job, draggable }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: job.id,
    disabled: !draggable,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-3 p-3 border rounded bg-white ${
        draggable ? "cursor-grab hover:border-slate-400" : "cursor-not-allowed bg-slate-50"
      }`}
      {...attributes}
      {...(draggable ? listeners : {})}
    >
      <span className="text-slate-400 text-lg">{draggable ? "≡" : "🔒"}</span>
      <div className="flex-1 min-w-0">
        <div className="font-mono text-xs text-slate-500 truncate">{job.id}</div>
        <div className="text-sm text-slate-900 truncate">
          {job.dataset_id} · {job.num_clusters} clusters
        </div>
      </div>
      <span className="text-xs text-slate-500">prio {job.priority}</span>
      <StatusBadge status={job.status} />
    </div>
  );
}
