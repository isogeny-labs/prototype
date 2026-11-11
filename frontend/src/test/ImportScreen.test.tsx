import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Import, SkippedItem } from "../api";
import { ImportScreen } from "../components/ImportScreen";
import { address, calls, claims, demoImport, mockApi, run, session, text } from "./fixtures";

const skippedItems: SkippedItem[] = [
  {
    name: "SHA-256",
    what: "Hash algorithm",
    source: "components[3] (bom-ref hash-sha256)",
    reason: "Hash algorithms are not checked in this version",
  },
  {
    name: "AES-256-GCM",
    what: "Cipher",
    source: "components[4] (bom-ref aes-gcm)",
    reason: "Ciphers on their own are not checked in this version",
  },
];

function renderImport(imp: Import | null, overrides: Partial<Parameters<typeof ImportScreen>[0]> = {}) {
  const props = {
    demoServer: session.demo_server,
    imp,
    onImported: vi.fn(),
    onImportFailed: vi.fn(),
    onAddressChanged: vi.fn(),
    onVerified: vi.fn(),
    ...overrides,
  };
  render(<ImportScreen {...props} />);
  return props;
}

describe("Import screen", () => {
  it("starts with only the drop zone and the demo button", () => {
    renderImport(null);
    expect(screen.getByLabelText("Choose a file to import").getAttribute("type")).toBe("file");
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Use demo file"]);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("loads the demo file through POST /api/import/demo", async () => {
    const fetchMock = mockApi({ "POST /api/import/demo": { body: demoImport } });
    const props = renderImport(null);
    fireEvent.click(screen.getByRole("button", { name: "Use demo file" }));
    await waitFor(() => expect(props.onImported).toHaveBeenCalledWith(demoImport));
    expect(calls(fetchMock)).toEqual(["POST /api/import/demo"]);
  });

  it("renders the claims table with source tags, the Demo data label and a tick box per address", () => {
    renderImport(demoImport);
    expect(screen.getByText("Demo data")).not.toBeNull();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Where", "What", "Claimed value"]);

    const rows = screen.getAllByTestId("claim-row");
    expect(rows).toHaveLength(3);
    const first = within(rows[0]!);
    expect(first.getByText("localhost:8443")).not.toBeNull();
    expect(first.getByText("TLS versions")).not.toBeNull();
    expect(first.getByText("localhost:8443 accepts TLS 1.3 only")).not.toBeNull();
    expect(first.getByText("TLS 1.3")).not.toBeNull();
    expect(first.getByText("from the file")).not.toBeNull();
    expect(first.getByText("components[0] (bom-ref tls-acme-pay)")).not.toBeNull();

    const ticks = screen.getAllByTestId("address-confirm");
    expect(ticks).toHaveLength(1);
    expect((ticks[0] as HTMLInputElement).checked).toBe(false);
    const label = screen.getByLabelText(/I own this system or am allowed to test it/);
    expect(label).toBe(ticks[0]);
    expect(text(ticks[0]!.closest("label"))).toContain("localhost:8443");
    expect(text(ticks[0]!.closest("label"))).toContain("127.0.0.1");
  });

  it("does not show the Demo data label for an uploaded file", () => {
    renderImport({ ...demoImport, is_demo: false, filename: "mine.csv", format: "csv" });
    expect(screen.queryByText("Demo data")).toBeNull();
  });

  it("only has the allowed buttons", () => {
    renderImport(demoImport);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Use demo file", "Verify claims"]);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("sends the tick to confirm-address and reports the answer", async () => {
    const confirmed = { ...address, confirmed: true };
    const fetchMock = mockApi({ "POST /api/import/7/confirm-address": { body: confirmed } });
    const props = renderImport(demoImport);
    fireEvent.click(screen.getByTestId("address-confirm"));
    await waitFor(() => expect(props.onAddressChanged).toHaveBeenCalledWith(confirmed));
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ address: "localhost:8443", confirmed: true });
  });

  it("keeps Verify claims off until every address is ticked", async () => {
    renderImport(demoImport);
    expect((screen.getByRole("button", { name: "Verify claims" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Tick the box for each address above first.")).not.toBeNull();
  });

  it("calls verify and shows a working state", async () => {
    let finish: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => (finish = resolve));
    const fetchMock = vi.fn(async () => {
      await gate;
      return new Response(JSON.stringify(run), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const props = renderImport({ ...demoImport, addresses: [{ ...address, confirmed: true }] });
    const button = screen.getByRole("button", { name: "Verify claims" });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(text(screen.getByRole("status"))).toContain("Checking each claim");
    finish?.();
    await waitFor(() => expect(props.onVerified).toHaveBeenCalledWith(run));
    expect(fetchMock.mock.calls[0]).toEqual(["/api/import/7/verify", expect.objectContaining({ method: "POST" })]);
  });

  it("needs no tick for a software-only import", () => {
    renderImport({ ...demoImport, claims: [claims[2]!], addresses: [] });
    expect(screen.queryByTestId("address-confirm")).toBeNull();
    expect((screen.getByRole("button", { name: "Verify claims" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("uploads a chosen file as raw bytes with its filename", async () => {
    const fetchMock = mockApi({ "POST /api/import/file?filename=my%20claims.csv": { body: demoImport } });
    const props = renderImport(null);
    const file = new File(["location,type,claim,value\n"], "my claims.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("Choose a file to import"), { target: { files: [file] } });
    await waitFor(() => expect(props.onImported).toHaveBeenCalled());
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.body).toBe(file);
    expect(init?.headers).toEqual({ "Content-Type": "application/octet-stream" });
  });

  it("uploads a dropped file", async () => {
    const fetchMock = mockApi({ "POST /api/import/file?filename=cbom.json": { body: demoImport } });
    const props = renderImport(null);
    const file = new File(["{}"], "cbom.json", { type: "application/json" });
    fireEvent.drop(screen.getByText(/Drop a file here/), { dataTransfer: { files: [file] } });
    await waitFor(() => expect(props.onImported).toHaveBeenCalled());
    expect(calls(fetchMock)).toEqual(["POST /api/import/file?filename=cbom.json"]);
  });

  it("shows an upload error with its line and field", async () => {
    mockApi({
      "POST /api/import/file?filename=broken.csv": {
        status: 422,
        body: { error: { message: "The value column is empty.", line: 3, field: "value" } },
      },
    });
    const props = renderImport(null);
    fireEvent.change(screen.getByLabelText("Choose a file to import"), { target: { files: [new File(["x"], "broken.csv")] } });
    const alert = await screen.findByRole("alert");
    expect(text(alert)).toContain("We couldn't read that file");
    expect(text(alert)).toContain("The value column is empty.");
    expect(text(alert)).toContain("Line 3");
    expect(text(alert)).toContain("Field: value");
    expect(props.onImported).not.toHaveBeenCalled();
  });

  it("tells the app to clear the previous file when an upload fails", async () => {
    mockApi({
      "POST /api/import/file?filename=broken.csv": {
        status: 422,
        body: { error: { message: "The value column is empty.", line: 3, field: "value" } },
      },
    });
    const props = renderImport(demoImport);
    const input = screen.getByLabelText("Choose a file to import");
    fireEvent.change(input, { target: { files: [new File(["x"], "broken.csv")] } });
    await screen.findByRole("alert");
    expect(props.onImportFailed).toHaveBeenCalledTimes(1);
    fireEvent.change(input, { target: { files: [new File(["x"], "notes.txt")] } });
    expect(props.onImportFailed).toHaveBeenCalledTimes(2);
  });

  it("does not show a skipped note when nothing was skipped or the field is absent", () => {
    renderImport(demoImport);
    expect(screen.queryByTestId("skipped-note")).toBeNull();
    const { skipped: _skipped, ...older } = demoImport;
    renderImport(older);
    expect(screen.queryByTestId("skipped-note")).toBeNull();
  });

  it("says when one item was skipped and lists it inside the disclosure", () => {
    renderImport({ ...demoImport, skipped: [skippedItems[0]!] });
    const note = screen.getByTestId("skipped-note");
    expect(note.tagName).toBe("DETAILS");
    expect((note as HTMLDetailsElement).open).toBe(false);
    expect(text(note.querySelector("summary"))).toBe("1 item skipped: not checked in this version");
    const items = within(note).getAllByTestId("skipped-item");
    expect(items).toHaveLength(1);
    expect(text(items[0])).toContain("SHA-256");
    expect(text(items[0])).toContain("Hash algorithm");
    expect(text(items[0])).toContain("components[3] (bom-ref hash-sha256)");
    expect(text(items[0])).toContain("Hash algorithms are not checked in this version");
  });

  it("counts several skipped items and adds no button for them", () => {
    renderImport({ ...demoImport, skipped: skippedItems });
    const note = screen.getByTestId("skipped-note");
    expect(text(note.querySelector("summary"))).toBe("2 items skipped: not checked in this version");
    const items = within(note).getAllByTestId("skipped-item");
    expect(items).toHaveLength(2);
    expect(items.every((item) => item.closest("details") === note)).toBe(true);
    expect(text(items[1])).toContain("AES-256-GCM");
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Use demo file", "Verify claims"]);
  });

  it("shows the line only once when the message already names it", async () => {
    mockApi({
      "POST /api/import/file?filename=broken.csv": {
        status: 422,
        body: { error: { message: "Line 3: The value column is empty.", line: 3, field: "value" } },
      },
    });
    renderImport(null);
    fireEvent.change(screen.getByLabelText("Choose a file to import"), { target: { files: [new File(["x"], "broken.csv")] } });
    const alert = await screen.findByRole("alert");
    expect(text(alert).match(/line 3/gi)).toHaveLength(1);
    expect(text(alert)).toContain("Line 3: The value column is empty.");
    expect(text(alert)).toContain("Field: value");
    expect(text(alert)).not.toContain("·");
  });

  it("refuses the wrong file type and oversized files without sending their contents", async () => {
    const fetchMock = mockApi({});
    renderImport(null);
    const input = screen.getByLabelText("Choose a file to import");
    fireEvent.change(input, { target: { files: [new File(["x"], "notes.txt")] } });
    expect(text(await screen.findByRole("alert"))).toContain("isn't a .json or .csv file");
    fireEvent.change(input, { target: { files: [new File([new Uint8Array(1024 * 1024 + 1)], "big.json")] } });
    await waitFor(() => expect(text(screen.getByRole("alert"))).toContain("larger than 1 MB"));
    // Only an empty body is sent, so the server forgets the previous file too; the contents stay here.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const [url, init] of fetchMock.mock.calls as [string, RequestInit][]) {
      expect(url).toContain("/api/import/file?filename=");
      expect((init.body as File).size).toBe(0);
    }
  });

  it("shows an address error and a stopped demo server plainly", () => {
    renderImport(
      { ...demoImport, addresses: [{ ...address, resolved_ip: null, error: "This address could not be found." }] },
      { demoServer: { address: "localhost:8443", running: false, error: "Port 8443 is already in use." } },
    );
    expect(screen.getByText("This address could not be found.")).not.toBeNull();
    expect(screen.getByText("The demo server at localhost:8443 isn't running")).not.toBeNull();
    expect(screen.getByText("Port 8443 is already in use.")).not.toBeNull();
  });
});
