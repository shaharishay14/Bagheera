import client from "./client.js";

export async function listJobs() {
  const { data } = await client.get("/api/v1/jobs");
  return data;
}

export async function getJobStatus(jobId) {
  const { data } = await client.get(`/api/v1/jobs/${jobId}/status`);
  return data;
}

export async function reorderJobs(orderedJobIds) {
  const { data } = await client.put("/api/v1/jobs/reorder", { ordered_job_ids: orderedJobIds });
  return data;
}

export async function getVisualization(jobId) {
  const { data } = await client.get(`/api/v1/visualization/${jobId}`);
  return data;
}
