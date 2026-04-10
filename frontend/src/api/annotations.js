import client from "./client.js";

export async function createAnnotation({ target_id, target_type, note }) {
  const { data } = await client.post("/api/v1/annotations", { target_id, target_type, note });
  return data;
}
