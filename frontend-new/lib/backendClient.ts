/**
 * Server-side HTTP client for the FastAPI backend.
 * Used ONLY inside Next.js API route handlers (BFF layer).
 * Never import this in browser components.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://backend:8000/api";

interface BackendError {
  detail?: string | { code: string; message: string };
}

class BackendClientError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "BackendClientError";
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const url = `${BACKEND_URL}${path}`;
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    // No Next.js caching — BFF routes are always fresh
    cache: "no-store",
  });

  if (!res.ok) {
    let message = `Backend ${method} ${path} → ${res.status}`;
    try {
      const err: BackendError = await res.json();
      if (typeof err.detail === "string") message = err.detail;
      else if (err.detail?.message) message = err.detail.message;
    } catch {
      // ignore parse errors
    }
    throw new BackendClientError(res.status, message);
  }

  return res.json() as Promise<T>;
}

export const backendClient = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown) => request<T>("POST", path, body),
};

export { BackendClientError };
