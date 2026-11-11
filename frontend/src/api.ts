// Typed client for the backend API. Everything the screens know about the
// server goes through here.

export type ClaimKind =
  | "protocol_versions"
  | "cipher_suites"
  | "key_exchange"
  | "certificate"
  | "signature_algorithm";

export type LocationKind = "server" | "software" | "unknown";

export type ResultValue = "True" | "False" | "Couldn't check";

export interface DemoServer {
  address: string;
  running: boolean;
  error: string | null;
}

export interface Session {
  setup_required: boolean;
  logged_in: boolean;
  mode: "demo";
  demo_server: DemoServer;
}

export interface Claim {
  id: number;
  ref: string;
  location: string;
  location_kind: LocationKind;
  kind: ClaimKind;
  claimed_value: string;
  text: string;
  source: string;
}

export interface Address {
  address: string;
  host: string;
  port: number;
  resolved_ip: string | null;
  is_loopback: boolean;
  confirmed: boolean;
  error: string | null;
}

/** Something in the file that this version doesn't check (for example a hash algorithm). */
export interface SkippedItem {
  name: string;
  what: string;
  source: string;
  reason: string;
}

export interface Import {
  id: number;
  filename: string;
  format: "cyclonedx-cbom" | "csv";
  is_demo: boolean;
  claims: Claim[];
  addresses: Address[];
  /** Always sent by the current backend; optional so an older reply doesn't break the screen. */
  skipped?: SkippedItem[];
}

export interface Evidence {
  title: string;
  command: string;
  output: string;
  started_at: string;
  duration_ms: number;
  tool: string;
  tool_version: string;
}

export interface Result {
  claim_id: number;
  claim: Claim;
  result: ResultValue;
  found: string;
  reason: string | null;
  evidence: Evidence[];
}

export interface VerifyRun {
  id: number;
  import_id: number;
  started_at: string;
  finished_at: string;
  results: Result[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly line: number | null;
  readonly field: string | null;

  constructor(status: number, message: string, line: number | null = null, field: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.line = line;
    this.field = field;
  }
}

let onUnauthorized: (() => void) | null = null;

/** The app registers this so it can show the login screen when the session ends. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toApiError(status: number, body: unknown): ApiError {
  if (isRecord(body)) {
    const err = body["error"];
    if (isRecord(err) && typeof err["message"] === "string") {
      return new ApiError(
        status,
        err["message"],
        typeof err["line"] === "number" ? err["line"] : null,
        typeof err["field"] === "string" ? err["field"] : null,
      );
    }
    if (typeof body["detail"] === "string") {
      return new ApiError(status, body["detail"]);
    }
  }
  return new ApiError(status, `Something went wrong (the server answered ${status}).`);
}

interface RequestOptions {
  method?: "GET" | "POST";
  json?: unknown;
  raw?: Blob;
  /** Don't treat 401 as "session ended" (used by the login call itself). */
  quiet401?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const init: RequestInit = { method: options.method ?? "GET", credentials: "same-origin" };
  if (options.json !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.json);
  } else if (options.raw !== undefined) {
    init.headers = { "Content-Type": "application/octet-stream" };
    init.body = options.raw;
  }

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Can't reach the app. Check that it is still running, then try again.");
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    if (response.status === 401 && !options.quiet401 && onUnauthorized) {
      onUnauthorized();
    }
    throw toApiError(response.status, body);
  }
  return body as T;
}

async function orNullOn404<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export const MAX_UPLOAD_BYTES = 1024 * 1024;

export const api = {
  getSession: () => request<Session>("/api/session"),

  setup: (password: string) =>
    request<{ ok: true }>("/api/setup", { method: "POST", json: { password }, quiet401: true }),

  login: (password: string) =>
    request<{ ok: true }>("/api/login", { method: "POST", json: { password }, quiet401: true }),

  importDemo: () => request<Import>("/api/import/demo", { method: "POST" }),

  /** Sends the file's raw bytes. The server only reads it as data. */
  importFile: (file: File) =>
    request<Import>(`/api/import/file?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      raw: file,
    }),

  getCurrentImport: () => orNullOn404(request<Import>("/api/import/current")),

  confirmAddress: (importId: number, address: string, confirmed: boolean) =>
    request<Address>(`/api/import/${importId}/confirm-address`, {
      method: "POST",
      json: { address, confirmed },
    }),

  verify: (importId: number) => request<VerifyRun>(`/api/import/${importId}/verify`, { method: "POST" }),

  getLatestVerify: (importId: number) => orNullOn404(request<VerifyRun>(`/api/import/${importId}/verify`)),
};

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}
