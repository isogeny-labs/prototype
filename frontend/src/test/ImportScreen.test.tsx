import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Import, ImportOtto, SkippedItem } from "../api";
import { ImportScreen } from "../components/ImportScreen";
import { LinkProvider } from "../components/related";
import { ReadOnlyProvider } from "../readOnly";
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

  it("opens a claim's details in a panel on a row click, and closes it again", () => {
    renderImport(demoImport);
    expect(screen.queryByTestId("claim-panel")).toBeNull();
    const first = screen.getAllByTestId("claim-row")[0]!;
    fireEvent.click(first);
    const panel = within(screen.getByTestId("claim-panel"));
    expect(panel.getByRole("heading", { level: 2, name: "localhost:8443" })).not.toBeNull();
    expect(panel.getByText("TLS versions")).not.toBeNull();
    expect(panel.getByText("localhost:8443 accepts TLS 1.3 only")).not.toBeNull();
    expect(panel.getByText("TLS 1.3")).not.toBeNull();
    expect(panel.getByText("components[0] (bom-ref tls-acme-pay)")).not.toBeNull();
    expect(first.getAttribute("aria-selected")).toBe("true");
    fireEvent.click(panel.getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("claim-panel")).toBeNull();
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
    await waitFor(() => expect(props.onImportFailed).toHaveBeenCalledTimes(2));
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

  it("shows the upload reply's notices as small notes under the claims table", async () => {
    const notices = [
      "Demo data: started the three demo test servers for this file on this computer (ports 8444, 8445, 8446).",
      "Port 8446 was already taken on this computer, so that test server didn't start.",
    ];
    const uploaded: Import = { ...demoImport, filename: "multi-target-demo.csv", format: "csv", notices };
    mockApi({ "POST /api/import/file?filename=multi-target-demo.csv": { body: uploaded } });
    const props = renderImport(null);
    expect(screen.queryByTestId("import-notice")).toBeNull();
    const file = new File(["location,type,claim,value\n"], "multi-target-demo.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("Choose a file to import"), { target: { files: [file] } });
    await waitFor(() => expect(props.onImported).toHaveBeenCalledWith(uploaded));

    // The app hands the reply back as the screen's file.
    cleanup();
    renderImport(uploaded);
    const shown = screen.getAllByTestId("import-notice");
    expect(shown.map((n) => n.textContent)).toEqual(notices);
    const table = screen.getByRole("table");
    expect(table.compareDocumentPosition(shown[0]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(shown[0]!.getAttribute("role")).toBeNull();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Use demo file", "Verify claims"]);
  });

  it("shows no notice for the demo file or when the reply has none", () => {
    renderImport(demoImport);
    expect(screen.queryByTestId("import-notice")).toBeNull();
    cleanup();
    renderImport({ ...demoImport, notices: [] });
    expect(screen.queryByTestId("import-notice")).toBeNull();
  });

  it("lists the settings the file carries under the claims, only when there are some", () => {
    const withSettings: Import = {
      ...demoImport,
      settings_title: "System settings from the file",
      settings: [
        { location: "localhost:8451", text: "Exposure: internet-facing. Data lifespan: long-lived." },
        { location: "localhost:8454", text: "Can it be changed: no." },
      ],
    };
    renderImport(withSettings);
    const box = within(screen.getByTestId("import-settings"));
    expect(box.getByRole("heading", { name: "System settings from the file" })).not.toBeNull();
    expect(screen.getAllByTestId("import-setting").map((li) => text(li))).toEqual([
      "localhost:8451 Exposure: internet-facing. Data lifespan: long-lived.",
      "localhost:8454 Can it be changed: no.",
    ]);
    expect(box.getByText("localhost:8451").className).toContain("font-mono");
    cleanup();

    renderImport({ ...demoImport, settings_title: "System settings from the file", settings: [] });
    expect(screen.queryByTestId("import-settings")).toBeNull();
    cleanup();
    // An older stored answer without the field.
    renderImport(demoImport);
    expect(screen.queryByTestId("import-settings")).toBeNull();
  });
});

describe("Import screen, phase 5b", () => {
  const headers = () => within(screen.getByRole("table", { name: "What the file claims" })).getAllByRole("columnheader").map((h) => text(h));

  it("draws an algorithm's plain name with the technical name under it", () => {
    renderImport(demoImport);
    const value = within(screen.getAllByTestId("claim-row")[1]!).getByTestId("algo-name");
    expect(Array.from(value.children).map((c) => c.textContent)).toEqual(["Classical signatures", "ECDSA P-256"]);
  });

  it("beside an open claim, a row is where and what and the claimed value; the panel links to its Verify result", () => {
    renderImport(demoImport);
    const full = headers();
    fireEvent.click(screen.getAllByTestId("claim-row")[0]!);
    expect(headers()).toEqual(["Where and what", "Claimed value"]);
    expect(headers().length).toBeLessThan(full.length);
    const panel = within(screen.getByTestId("claim-panel"));
    expect(panel.getByTestId("claim-to-verify").textContent).toBe("Its Verify result");
    fireEvent.click(panel.getByRole("button", { name: "Close details" }));
    expect(headers()).toEqual(full);
  });

  it("opens the claim a link names", () => {
    renderImport(demoImport, { openItem: "claim-3" });
    expect(within(screen.getByTestId("claim-panel")).getByRole("heading", { level: 2 }).textContent).toContain("acme-sign 1.4.2");
  });

  it("keeps a linked claim's panel closed once the person has closed it, also when the file's data is read again", () => {
    // The page gets the file again whenever something on it is refreshed (an address ticked, Otto's line read again
    // on opening Import). A link opens its claim when the link or the file changes, never on such a read.
    const props = { demoServer: session.demo_server, onImported: vi.fn(), onImportFailed: vi.fn(), onAddressChanged: vi.fn(), onVerified: vi.fn() };
    const { rerender } = render(<ImportScreen {...props} imp={demoImport} openItem="claim-3" />);
    fireEvent.click(within(screen.getByTestId("claim-panel")).getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("claim-panel")).toBeNull();
    rerender(<ImportScreen {...props} imp={{ ...demoImport }} openItem="claim-3" />);     // the same file, read again
    expect(screen.queryByTestId("claim-panel")).toBeNull();
    // another file with that link opens its claim, as before
    rerender(<ImportScreen {...props} imp={{ ...demoImport, id: demoImport.id + 1 }} openItem="claim-3" />);
    expect(screen.getByTestId("claim-panel")).not.toBeNull();
  });
});

describe("Import screen: what Otto found (phase 5c)", () => {
  /** Import's line about Otto as the backend sends it once a file is in and a test pack is installed. */
  const FOUND: ImportOtto = {
    count: 2,
    label: "From Otto",
    text: "Otto found 2 checks that may apply: 2 published weaknesses with a test, for acme-sign 1.4.2.",
    note: "Nothing runs on import. You accept or reject each proposed check on Advisories.",
    link: { page: "advisories", item: null },
    link_label: "Open Advisories",
  };
  const NONE_FIT: ImportOtto = {
    ...FOUND,
    count: 0,
    text: "Otto found no check that may apply to this file: no signing program in this file checks ECDSA P-256 signatures.",
    note: "Nothing runs on import.",
  };
  const NO_PACK: ImportOtto = {
    count: 0,
    label: "From Otto",
    text: "Otto has nothing to propose for this file yet: no test pack is installed.",
    note: "Test packs are installed in Settings. Nothing runs on import.",
    link: { page: "settings", item: null, section: "test-packs" },
    link_label: "Open Settings",
  };

  /** The page as the app shows it: inside the open assessment, so a link the backend sends has somewhere to go. */
  function renderInAssessment(imp: Import | null, readOnly = false) {
    const props = { demoServer: session.demo_server, imp, onImported: vi.fn(), onImportFailed: vi.fn(), onAddressChanged: vi.fn(), onVerified: vi.fn() };
    render(
      <ReadOnlyProvider readOnly={readOnly}>
        <LinkProvider assessmentId={101} planId={1}>
          <ImportScreen {...props} />
        </LinkProvider>
      </ReadOnlyProvider>,
    );
    return props;
  }
  const line = () => screen.getByTestId("import-otto");

  it("says how many checks may apply once a file is in, with the way to Advisories, in the backend's words", () => {
    const fetchMock = mockApi({});
    renderInAssessment({ ...demoImport, otto: FOUND });
    expect(line().getAttribute("data-count")).toBe("2");
    expect(text(within(line()).getByTestId("import-otto-label"))).toBe("From Otto");
    expect(text(within(line()).getByTestId("import-otto-text"))).toBe(FOUND.text);
    expect(text(within(line()).getByTestId("import-otto-note"))).toBe(FOUND.note);
    const link = within(line()).getByRole("link", { name: "Open Advisories" });
    expect(link.getAttribute("href")).toBe("#/a/101/advisories");
    // A line and a link: showing it asks for nothing and sends nothing.
    expect(calls(fetchMock)).toEqual([]);
  });

  it("is a link, never a button: bringing a file in adds nothing and runs nothing", () => {
    const fetchMock = mockApi({});
    const props = renderInAssessment({ ...demoImport, otto: FOUND });
    expect(within(line()).queryAllByRole("button")).toHaveLength(0);
    // The page's buttons are the ones it always had.
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Use demo file", "Verify claims"]);
    fireEvent.click(within(line()).getByRole("link", { name: "Open Advisories" }));
    expect(calls(fetchMock)).toEqual([]);
    expect(props.onVerified).not.toHaveBeenCalled();
    expect(props.onImported).not.toHaveBeenCalled();
    window.history.replaceState(null, "", "#/");   // (the link moved the address; put it back for the tests after this one)
  });

  it("sits with what the file claims, before the address ticks and Verify claims", () => {
    mockApi({});
    renderInAssessment({ ...demoImport, otto: FOUND });
    const table = screen.getByRole("table", { name: "What the file claims" });
    const verify = screen.getByRole("button", { name: "Verify claims" });
    expect(table.compareDocumentPosition(line()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(line().compareDocumentPosition(verify) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(line().compareDocumentPosition(screen.getAllByTestId("address-confirm")[0]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("with no check that fits it says why, with the same way to Advisories", () => {
    mockApi({});
    renderInAssessment({ ...demoImport, otto: NONE_FIT });
    expect(line().getAttribute("data-count")).toBe("0");
    expect(text(within(line()).getByTestId("import-otto-text"))).toBe(NONE_FIT.text);
    expect(text(within(line()).getByTestId("import-otto-note"))).toBe("Nothing runs on import.");
    expect(within(line()).getByRole("link", { name: "Open Advisories" }).getAttribute("href")).toBe("#/a/101/advisories");
  });

  it("with no test pack installed it says so and points to Settings, Test packs", () => {
    mockApi({});
    renderInAssessment({ ...demoImport, otto: NO_PACK });
    expect(line().getAttribute("data-count")).toBe("0");
    expect(text(within(line()).getByTestId("import-otto-text"))).toBe(NO_PACK.text);
    expect(within(line()).getByRole("link", { name: "Open Settings" }).getAttribute("href")).toBe("#/settings?section=test-packs");
  });

  it("draws nothing when the answer carries no such line, a null one, or no file is in", () => {
    mockApi({});
    renderInAssessment(demoImport);
    expect(screen.queryByTestId("import-otto")).toBeNull();
    cleanup();
    renderInAssessment({ ...demoImport, otto: null });
    expect(screen.queryByTestId("import-otto")).toBeNull();
    cleanup();
    renderInAssessment(null);
    expect(screen.queryByTestId("import-otto")).toBeNull();
  });

  it("stays readable in a closed assessment: it is a way to a page, not an action", () => {
    mockApi({});
    renderInAssessment({ ...demoImport, otto: FOUND }, true);
    expect(text(within(line()).getByTestId("import-otto-text"))).toBe(FOUND.text);
    expect(within(line()).getByRole("link", { name: "Open Advisories" }).getAttribute("href")).toBe("#/a/101/advisories");
  });

  it("adds no word of its own: every word in the line is one the backend sent", () => {
    mockApi({});
    renderInAssessment({ ...demoImport, otto: FOUND });
    const squeezed = (words: string) => words.replace(/\s+/g, "");
    expect(squeezed(text(line()))).toBe(squeezed([FOUND.label, FOUND.text, FOUND.note, FOUND.link_label].join("")));
  });
});
