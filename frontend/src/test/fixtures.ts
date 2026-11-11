import { vi } from "vitest";
import type { Address, Claim, Import, Session, VerifyRun } from "../api";

export const session: Session = {
  setup_required: false,
  logged_in: true,
  mode: "demo",
  demo_server: { address: "localhost:8443", running: true, error: null },
};

export const claims: Claim[] = [
  {
    id: 1,
    ref: "tls-acme-pay",
    location: "localhost:8443",
    location_kind: "server",
    kind: "protocol_versions",
    claimed_value: "TLS 1.3",
    text: "localhost:8443 accepts TLS 1.3 only",
    source: "components[0] (bom-ref tls-acme-pay)",
  },
  {
    id: 2,
    ref: "cert-acme-pay",
    location: "localhost:8443",
    location_kind: "server",
    kind: "certificate",
    claimed_value: "ECDSA P-256",
    text: "localhost:8443 certificate is ECDSA P-256",
    source: "components[1] (bom-ref cert-acme-pay)",
  },
  {
    id: 3,
    ref: "acme-sign",
    location: "acme-sign 1.4.2",
    location_kind: "software",
    kind: "signature_algorithm",
    claimed_value: "ECDSA P-256",
    text: "signing component is acme-sign 1.4.2 implementing ECDSA P-256",
    source: "components[2] (bom-ref acme-sign)",
  },
];

export const address: Address = {
  address: "localhost:8443",
  host: "localhost",
  port: 8443,
  resolved_ip: "127.0.0.1",
  is_loopback: true,
  confirmed: false,
  error: null,
};

export const demoImport: Import = {
  id: 7,
  filename: "acme-pay-cbom.json",
  format: "cyclonedx-cbom",
  is_demo: true,
  claims,
  addresses: [address],
  skipped: [],
};

const evidence = {
  title: "TLS 1.2 handshake",
  command: "openssl s_client -connect localhost:8443 -tls1_2",
  output: "Protocol  : TLSv1.2\nCipher    : ECDHE-ECDSA-AES128-SHA",
  started_at: "2026-11-11T10:00:00Z",
  duration_ms: 42,
  tool: "OpenSSL",
  tool_version: "3.0.13",
};

export const run: VerifyRun = {
  id: 1,
  import_id: 7,
  started_at: "2026-11-11T10:00:00Z",
  finished_at: "2026-11-11T10:00:02Z",
  results: [
    {
      claim_id: 1,
      claim: claims[0]!,
      result: "False",
      found: "Accepts TLS 1.3 and TLS 1.2 (with ECDHE-ECDSA-AES128-SHA). Refuses TLS 1.1 and TLS 1.0.",
      reason: null,
      evidence: [evidence],
    },
    {
      claim_id: 2,
      claim: claims[1]!,
      result: "True",
      found: "The certificate uses an ECDSA P-256 key.",
      reason: null,
      evidence: [{ ...evidence, title: "Certificate read", command: "openssl x509 -noout -text" }],
    },
    {
      claim_id: 3,
      claim: claims[2]!,
      result: "Couldn't check",
      found: "Nothing was measured.",
      reason: "The component did not start within the time limit.",
      evidence: [],
    },
  ],
};

type Reply = { status?: number; body: unknown };
type Route = Reply | ((init: RequestInit | undefined) => Reply);

/** Replaces fetch with a table of "METHOD /path" -> reply. Unknown calls fail the test loudly. */
export function mockApi(routes: Record<string, Route>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const route = routes[key];
    if (!route) throw new Error(`Unexpected request: ${key}`);
    const reply = typeof route === "function" ? route(init) : route;
    return new Response(JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function calls(fetchMock: ReturnType<typeof mockApi>): string[] {
  return fetchMock.mock.calls.map(([input, init]) => `${init?.method ?? "GET"} ${String(input)}`);
}

export const notFound: Reply = { status: 404, body: { error: { message: "Not found", line: null, field: null } } };

/** The visible text of an element with runs of whitespace collapsed (empty if the element is missing). */
export function text(el: Element | null | undefined): string {
  return (el?.textContent ?? "").replace(/\s+/g, " ").trim();
}
