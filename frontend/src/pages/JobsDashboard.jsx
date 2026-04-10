import { useEffect, useState, useCallback } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { listJobs, reorderJobs } from "../api/jobs.js";
import JobRow from "../components/JobRow.jsx";
import Toast from "../components/Toast.jsx";

const POLL_MS = 2000;

export default function JobsDashboard() {
  const [jobs, setJobs] = useState([]);
  const [toast, setToast] = useState({ message: "", kind: "info" });

  const refresh = useCallback(async () => {
    try {
      const data = await listJobs();
      setJobs(data);
    } catch (err) {
      setToast({ message: `Failed to load jobs: ${err.message}`, kind: "error" });
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const queued = jobs.filter((j) => j.status === "Queued");
  const others = jobs.filter((j) => j.status !== "Queued");

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  async function onDragEnd(event) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = queued.findIndex((j) => j.id === active.id);
    const newIndex = queued.findIndex((j) => j.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const reordered = arrayMove(queued, oldIndex, newIndex);
    // Optimistic update
    setJobs([...reordered, ...others]);

    try {
      await reorderJobs(reordered.map((j) => j.id));
      refresh();
    } catch (err) {
      const status = err?.response?.status;
      const msg =
        status === 409
          ? "Cannot reorder while a job is processing"
          : `Reorder failed: ${err.message}`;
      setToast({ message: msg, kind: "error" });
      refresh();
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Jobs Dashboard</h1>

      <section>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-2">
          Queued ({queued.length}) · drag to reorder
        </h2>
        {queued.length === 0 ? (
          <p className="text-sm text-slate-500">No queued jobs.</p>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={queued.map((j) => j.id)} strategy={verticalListSortingStrategy}>
              <div className="space-y-2">
                {queued.map((job) => (
                  <JobRow key={job.id} job={job} draggable />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-2">
          Active &amp; Finished ({others.length})
        </h2>
        {others.length === 0 ? (
          <p className="text-sm text-slate-500">Nothing here yet.</p>
        ) : (
          <div className="space-y-2">
            {others.map((job) => (
              <JobRow key={job.id} job={job} draggable={false} />
            ))}
          </div>
        )}
      </section>

      <Toast
        message={toast.message}
        kind={toast.kind}
        onClose={() => setToast({ message: "", kind: "info" })}
      />
    </div>
  );
}
