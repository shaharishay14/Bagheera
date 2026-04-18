import client from "./client.js";

export async function createAnnotation({ target_id, target_type, note }) {
  const { data } = await client.post("/api/v1/annotations", { target_id, target_type, note });
  return data;
}

export async function listAnnotations({ targetId, targetType } = {}) {
  const params = {};
  if (targetId) params.target_id = targetId;
  if (targetType && targetType !== "all") params.target_type = targetType;
  const { data } = await client.get("/api/v1/annotations", { params });
  return data;
}

export async function deleteAnnotation(annotationId) {
  await client.delete(`/api/v1/annotations/${annotationId}`);
}
