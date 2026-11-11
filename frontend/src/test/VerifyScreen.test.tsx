import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VerifyScreen } from "../components/VerifyScreen";
import { demoImport, run, text } from "./fixtures";

function renderVerify(isDemo = true) {
  const onContinue = vi.fn();
  render(<VerifyScreen imp={{ ...demoImport, is_demo: isDemo }} run={run} onContinue={onContinue} />);
  return onContinue;
}

describe("Verify screen", () => {
  it("shows one row per claim with the claim, what we found and a text badge", () => {
    renderVerify();
    const rows = screen.getAllByTestId("result-row");
    expect(rows).toHaveLength(3);
    expect(screen.getAllByTestId("result-badge").map((b) => b.textContent)).toEqual(["False", "True", "Couldn't check"]);

    const first = within(rows[0]!);
    expect(first.getByText("localhost:8443 accepts TLS 1.3 only")).not.toBeNull();
    expect(first.getByText("from the file")).not.toBeNull();
    expect(first.getByText(/Accepts TLS 1.3 and TLS 1.2/)).not.toBeNull();
    expect(first.getByText("measured")).not.toBeNull();
  });

  it("shows the reason for Couldn't check", () => {
    renderVerify();
    const row = within(screen.getAllByTestId("result-row")[2]!);
    expect(row.getByText("The component did not start within the time limit.")).not.toBeNull();
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

  it("expands and collapses the evidence for a row", async () => {
    renderVerify();
    const row = within(screen.getAllByTestId("result-row")[0]!);
    const toggle = row.getByRole("button", { name: "Evidence" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(row.queryByText("TLS 1.2 handshake")).toBeNull();

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(row.getByText("TLS 1.2 handshake")).not.toBeNull();
    expect(row.getByText("openssl s_client -connect localhost:8443 -tls1_2")).not.toBeNull();
    const output = row.getByText(/Protocol : TLSv1\.2/);
    expect(output.tagName).toBe("PRE");
    expect(text(output)).toContain("ECDHE-ECDSA-AES128-SHA");
    expect(row.getByText(/42 ms/)).not.toBeNull();
    expect(row.getByText(/OpenSSL 3.0.13/)).not.toBeNull();
    expect(row.getByText("Time:")).not.toBeNull();

    fireEvent.click(toggle);
    expect(row.queryByText("TLS 1.2 handshake")).toBeNull();
  });

  it("says so when a row has no evidence", async () => {
    renderVerify();
    const row = within(screen.getAllByTestId("result-row")[2]!);
    fireEvent.click(row.getByRole("button", { name: "Evidence" }));
    expect(row.getByText(/Nothing was run for this claim/)).not.toBeNull();
  });

  it("only has the allowed buttons", () => {
    renderVerify();
    expect(screen.getAllByRole("button").map((b) => b.textContent?.replace(/[▸▾]/g, "").trim())).toEqual([
      "Evidence",
      "Evidence",
      "Evidence",
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
    fireEvent.click(within(screen.getAllByTestId("result-row")[0]!).getByRole("button", { name: "Evidence" }));
    const command = screen.getByText("openssl s_client -connect localhost:8443 -tls1_2");
    for (const el of [command, document.querySelector("pre")!]) {
      expect(el.className).toContain("whitespace-pre-wrap");
      expect(el.className).toContain("break-words");
      expect(el.className).not.toContain("break-all");
    }
  });
});
