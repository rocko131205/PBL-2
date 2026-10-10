/** Thin fetch wrapper: same-origin cookies, CSRF double-submit header, uniform errors. */

export class ApiError extends Error {
  status: number;
  /** Per-field messages when the server returns {errors: {...}} (e.g. registration). */
  fields: Record<string, string>;
  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

function cookie(name: string): string {
  const hit = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return hit ? decodeURIComponent(hit.split("=")[1]) : "";
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();
/** Called when any request comes back 401 (session expired / revoked / timed out). */
export const onUnauthorized = (fn: Listener) => {
  unauthorizedListeners.add(fn);
  return () => void unauthorizedListeners.delete(fn);
};

interface Options {
  method?: string;
  json?: unknown;
  form?: FormData;
  /** Skip the global 401 handler (login/register legitimately return 401). */
  silent401?: boolean;
  signal?: AbortSignal;
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const method = opts.method ?? (opts.json || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form; // the browser sets the multipart boundary itself
  }
  if (method !== "GET") headers["X-CSRF-Token"] = cookie("fv_csrf");

  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, headers, body, credentials: "same-origin", signal: opts.signal });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }

  if (res.status === 401 && !opts.silent401) unauthorizedListeners.forEach((fn) => fn());
  if (res.ok) {
    if (res.status === 204) return undefined as T;
    const type = res.headers.get("content-type") ?? "";
    return (type.includes("json") ? res.json() : res.text()) as Promise<T>;
  }

  let message = `Request failed (${res.status})`;
  let fields: Record<string, string> = {};
  try {
    const data = await res.json();
    if (typeof data.detail === "string") message = data.detail;
    else if (Array.isArray(data.detail)) message = "Please check the highlighted fields.";
    if (data.errors && typeof data.errors === "object") {
      fields = data.errors;
      message = "Please check the highlighted fields.";
    }
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(res.status, message, fields);
}
