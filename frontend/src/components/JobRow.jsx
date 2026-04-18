import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import StatusBadge from "./StatusBadge.jsx";

function DragHandle() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="currentColor"
      className="text-panther-300 flex-shrink-0"
      aria-hidden="true"
    >
      <rect y="2" width="14" height="1.5" rx="0.75" />
      <rect y="6.25" width="14" height="1.5" rx="0.75" />
      <rect y="10.5" width="14" height="1.5" rx="0.75" />
    </svg>
  );
}

function PadlockIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="text-panther-300 flex-shrink-0"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z"
        clipRule="evenodd"
      />
    </svg>
  );
}

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
      className={`flex items-center gap-3 p-3 border rounded-xl bg-white transition-colors ${
        draggable
          ? "cursor-grab hover:border-panther-400/50 hover:bg-panther-50/50"
          : "bg-panther-50/30 opacity-80"
      }`}
      {...attributes}
      {...(draggable ? listeners : {})}
    >
      {draggable ? <DragHandle /> : <PadlockIcon />}

      <div className="flex-1 min-w-0">
        <div className="font-mono text-xs text-panther-300 truncate">{job.id.slice(0, 8)}</div>
        <div className="text-sm text-panther-900 truncate">{job.dataset_id}</div>
        <div className="font-mono text-xs text-panther-500">
          {job.encoder} · {job.num_clusters} clusters
        </div>
      </div>

      <StatusBadge status={job.status} />
    </div>
  );
}
