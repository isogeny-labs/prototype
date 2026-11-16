import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VerifyScreen } from "../components/VerifyScreen";
import { demoImport, run, text } from "./fixtures";

function renderVerify(isDemo = true) {
  const onContinue = vi.fn();
  render(<VerifyScreen imp={{ ...demoImport, is_demo: isDemo }} run={run} onContinue={onContinue} />);
  return onContinue;
}

/** The words of a result chip (its last child; the symbol comes first). */
const chipWords = (el: HTMLElement) => el.lastElementChild?.textContent;
/** The right-side panel that holds one opened claim's details. */
const panel = () => within(screen.getByTestId("detail-panel"));

describe("Verify screen", () => {
  it("shows one row per claim with the claim, a text badge and the plain sentence on top", () => {
    renderVerify();
    const rows = screen.getAllByTestId("result-row");
    expect(rows).toHaveLength(3);
    expect(screen.getAllByTestId("result-badge").map(chipWords)).toEqual(["False", "True", "Couldn't check"]);
    expect(screen.getAllByTestId("verify-summary").map((s) => s.textContent)).toEqual(run.results.map((r) => r.summary));

    const first = within(rows[0]!);
    expect(first.getByText("localhost:8443 accepts TLS 1.3 only")).not.toBeNull();
    expect(first.getByText("from the file")).not.toBeNull();
    // The technical words stay folded until the user opens them.
    expect(first.queryByText(/Accepts TLS 1.3 and TLS 1.2/)).toBeNull();
    expect(first.queryByText("measured")).toBeNull();
    expect(first.queryByText("What we found")).toBeNull();
  });

  it("keeps the technical finding, the badge meaning and the evidence in one fold", () => {
    renderVerify();
    const row = within(screen.getAllByTestId("result-row")[0]!);
    const toggle = row.getByTestId("verify-details-toggle");
    expect(toggle.textContent).toContain("Details and evidence");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("detail-panel")).toBeNull();

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const details = panel();
    expect(details.getByText("What we found")).not.toBeNull();
    expect(details.getByText(/Accepts TLS 1.3 and TLS 1.2/)).not.toBeNull();
    expect(details.getAllByText("measured").length).toBeGreaterThan(0);
    expect(details.getByText("The claim doesn't match what we measured.")).not.toBeNull();
    expect(details.getByText("TLS 1.2 handshake")).not.toBeNull();
  });

  it("shows an Also noticed note as a side note, not a result, and only where there is one", () => {
    renderVerify();
    const rows = screen.getAllByTestId("result-row");
    const notes = screen.getAllByTestId("also-noticed");
    expect(notes).toHaveLength(1);
    expect(rows[1]!.contains(notes[0]!)).toBe(true);
    expect(text(notes[0])).toBe(
      "Also noticed: While checking the certificate, the handshakes showed this server also accepts TLS 1.0 and TLS 1.1.",
    );
    // Visible without opening the fold, never drawn as a badge or in a result colour.
    expect(notes[0]!.getAttribute("data-testid")).not.toBe("result-badge");
    expect(notes[0]!.className).not.toMatch(/amber|green|red|emerald/);
    expect(within(rows[1]!).getAllByTestId("result-badge").map(chipWords)).toEqual(["True"]);
  });

  it("shows the reason for Couldn't check inside the fold", () => {
    renderVerify();
    const row = within(screen.getAllByTestId("result-row")[2]!);
    expect(screen.queryByText("The component did not start within the time limit.")).toBeNull();
    fireEvent.click(row.getByTestId("verify-details-toggle"));
    expect(panel().getByText("The component did not start within the time limit.")).not.toBeNull();
  });

  it("carries the exact disclaimer line and the Demo data label", () => {
    renderVerify();
    expect(
      screen.getByText("Passing these tests doesn't prove a system secure. It shows these specific checks passed."),
    ).not.toBeNull();
    expect(screen.getByText("Demo data")).not.toBeNull();
  });

  it("hides the Demo data label for the user's own file", () => {
    renderVerify(false);
    expect(screen.queryByText("Demo data")).toBeNull();
  });

  it("expands and collapses the details and evidence for a row", async () => {
    renderVerify();
    const row = within(screen.getAllByTestId("result-row")[0]!);
    const toggle = row.getByRole("button", { name: "Details and evidence" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("TLS 1.2 handshake")).toBeNull();

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const details = panel();
    expect(details.getByText("TLS 1.2 handshake")).not.toBeNull();
    expect(details.getByText("openssl s_client -connect localhost:8443 -tls1_2")).not.toBeNull();
    const output = details.getByText(/Protocol : TLSv1\.2/);
    expect(output.tagName).toBe("PRE");
    expect(text(output)).toContain("ECDHE-ECDSA-AES128-SHA");
    expect(details.getByText(/42 ms/)).not.toBeNull();
    expect(details.getByText(/OpenSSL 3.0.13/)).not.toBeNull();
    expect(details.getByText("Time:")).not.toBeNull();

    fireEvent.click(toggle);
    expect(screen.queryByText("TLS 1.2 handshake")).toBeNull();
  });

  it("says so when a row has no evidence", async () => {
    renderVerify();
    const row = within(screen.getAllByTestId("result-row")[2]!);
    fireEvent.click(row.getByRole("button", { name: "Details and evidence" }));
    expect(panel().getByText(/Nothing was run for this claim/)).not.toBeNull();
  });

  it("only has the allowed buttons", () => {
    renderVerify();
    expect(screen.getAllByRole("button").map((b) => b.textContent?.replace(/[▸▾]/g, "").trim())).toEqual([
      "Details and evidence",
      "Details and evidence",
      "Details and evidence",
      "Continue to tests",
    ]);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("continues to tests", async () => {
    const onContinue = renderVerify();
    fireEvent.click(screen.getByRole("button", { name: "Continue to tests" }));
    expect(onContinue).toHaveBeenCalledOnce();
  });
  it("wraps long evidence lines at spaces instead of splitting words", () => {
    renderVerify();
    fireEvent.click(within(screen.getAllByTestId("result-row")[0]!).getByRole("button", { name: "Details and evidence" }));
    const command = screen.getByText("openssl s_client -connect localhost:8443 -tls1_2");
    for (const el of [command, document.querySelector("pre")!]) {
      expect(el.className).toContain("whitespace-pre-wrap");
      expect(el.className).toContain("break-words");
      expect(el.className).not.toContain("break-all");
    }
  });
});
