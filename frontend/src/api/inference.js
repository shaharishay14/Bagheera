import client from "./client.js";

export async function submitInference({ dataset_id, num_clusters }) {
  const { data } = await client.post("/api/v1/inference", { dataset_id, num_clusters });
  return data;
}
