import client from "./client.js";

export async function submitInference({
  dataset_id,
  num_clusters,
  encoder = "uni",
  em_iter = 1,
  tau = 1.0,
  out_type = "allcat",
}) {
  const { data } = await client.post("/api/v1/inference", {
    dataset_id,
    num_clusters,
    encoder,
    em_iter,
    tau,
    out_type,
  });
  return data;
}
