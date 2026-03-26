export const API_BASE_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "") ?? "http://localhost:8030";

export const API_PREFIX = `${API_BASE_URL}/api`;
