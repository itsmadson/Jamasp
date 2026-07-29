export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    /** The raw `detail` value. FastAPI sends an object for structured errors,
     *  and flattening it to a string would discard the structure. */
    readonly payload: unknown = null,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    // The session cookie is httpOnly: the browser attaches it, JS never reads it.
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = response.statusText || `request failed with ${response.status}`;
    let payload: unknown = null;
    try {
      const body = await response.json();
      payload = body?.detail ?? null;
      if (typeof payload === "string") {
        detail = payload;
      } else if (payload && typeof payload === "object" && "message" in payload) {
        detail = String((payload as { message: unknown }).message);
      }
    } catch {
      // Non-JSON error body (proxy timeout, gateway page): keep the status text.
    }
    throw new ApiError(response.status, detail, payload);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
