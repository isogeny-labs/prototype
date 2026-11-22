import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProofBlock } from "../components/otto/ProofBlock";
import { ProposalCard } from "../components/otto/ProposalCard";
import { calls, mockApi, text } from "./fixtures";
import { proof, proofBlock } from "./proofFixtures";
import { acceptedProposal, proposal, rejectedProposal } from "./proposalFixtures";

/** Sandbox research (a prototype): "How this test was proven" on a proposal. The block only shows: every word and
 * every count is the backend's, the counts are the separate reviewer's, and showing it sends nothing. */

const ID = "check-cve-2022-21449-f3ea2161c217";
const route = (decision: string) => `POST /api/plans/7/otto/proposals/${ID}/${decision}`;
const withProof = (over = {}) => proposal({ proof: proof(), ...over });

describe("How this test was proven", () => {
  it("is folded under its title and its Sandbox copy label, and opening it sends nothing", () => {
    const fetchMock = mockApi({});
    render(<ProofBlock proof={proof()} />);
    const block = screen.getByTestId("proof-block") as HTMLDetailsElement;
    expect(block.open).toBe(false);
    expect(text(block.querySelector("summary")!)).toContain("How this test was proven");
    expect(text(screen.getByTestId("sandbox-copy-label"))).toBe("Sandbox copy");
    fireEvent.click(block.querySelector("summary")!);
    expect(calls(fetchMock)).toEqual([]);
  });

  it("lists every part of the trial with its count and what had to happen, and never a Passed or a Failed", () => {
    render(<ProofBlock proof={proof()} open />);
    const rows = screen.getAllByTestId("proof-row");
    expect(rows.map((r) => r.getAttribute("data-part"))).toEqual(["reference", "affected", "fixed", "control", "more-fixed-1", "more-fixed-2"]);
    const affected = rows[1]!;
    expect(text(affected)).toContain("starkbank-ecdsa 2.0.0 (the version the advisory names as affected)");
    expect(text(within(affected).getByTestId("proof-count"))).toBe("1 of 64 cases wrong");
    expect(text(affected)).toContain("What had to happen: At least one case wrong");
    expect(text(within(rows[2]!).getByTestId("proof-count"))).toBe("All 64 cases right");
    expect(text(within(rows[3]!).getByTestId("proof-count"))).toBe("64 of 64 cases wrong");
    const all = text(screen.getByTestId("proof-block"));
    for (const word of ["Passed", "Failed", "secure", "severity", "score"]) expect(all).not.toContain(word);
    // only the reviewer's counts are called the reviewer's: the control's is the pinned trial script's, and the note says so
    expect(all).toContain("for the library's copies and for our reference library are the separate reviewer's");
    expect(all).toContain("The control's count is made by the pinned trial script");
  });

  it("says when the trial was registered, what it froze, how it was judged, that the replay was no outside party, and what it does not show", () => {
    render(<ProofBlock proof={proof()} open />);
    expect(text(screen.getByTestId("proof-registered"))).toContain("before the first run");
    expect(text(screen.getByTestId("proof-registered"))).toContain("the registration is entry 13 and the first run is entry 14");
    const pins = screen.getByTestId("proof-pins");
    expect(text(pins)).toContain(`What was frozen, by SHA-256 (${proofBlock.registered.pins.length})`);
    expect(text(pins)).toContain(proofBlock.registered.pins[0]!.name);
    expect(text(screen.getByTestId("proof-judged"))).toContain("nothing was run again to get a better draw");
    expect(text(screen.getByTestId("proof-replayed"))).toContain("Not by an outside party");
    expect(text(screen.getByTestId("proof-not-shown"))).toContain("It does not say how serious the weakness is");
  });

  it("shows the code that asked the library only after Show, as text, with the second author's version beside it", () => {
    const fetchMock = mockApi({});
    render(<ProofBlock proof={proof()} open />);
    const code = screen.getByTestId("asking-code");
    expect(text(within(code).getByTestId("asking-code-label"))).toBe("Written by Otto");
    expect(text(within(code).getByTestId("asking-code-agree"))).toContain("gave the same answer on every case");
    expect(text(within(code).getByTestId("asking-code-known"))).toContain("24 fresh questions");
    expect(screen.queryByTestId("asking-code-source")).toBeNull();
    const toggle = within(code).getByTestId("asking-code-toggle");
    expect(text(toggle)).toBe("Show the code");
    fireEvent.click(toggle);
    expect(text(toggle)).toBe("Hide the code");
    const source = screen.getByTestId("asking-code-source");
    expect(source.tagName).toBe("PRE");
    expect(source.textContent).toContain("def check_signature(public_key, message, signature):");
    expect(screen.getByTestId("asking-code-second-source").textContent).toContain("parsed = Signature.fromDer(signature)");
    expect(screen.getByTestId("asking-code-second-source").textContent).not.toBe(source.textContent);
    fireEvent.click(toggle);
    expect(screen.queryByTestId("asking-code-source")).toBeNull();
    expect(calls(fetchMock)).toEqual([]);
  });

  it("the app's own asking code carries no Written by Otto tag and no second version", () => {
    const ours = proof();
    ours.code = { ...ours.code, label: null, second: null, agree_line: null };
    render(<ProofBlock proof={ours} open />);
    expect(screen.queryByTestId("asking-code-label")).toBeNull();
    expect(screen.queryByTestId("asking-code-agree")).toBeNull();
    fireEvent.click(screen.getByTestId("asking-code-toggle"));
    expect(screen.queryByTestId("asking-code-second")).toBeNull();
  });

  it("names every public copy with where it came from, and every version that was left out with the reason", () => {
    render(<ProofBlock proof={proof()} open />);
    const copies = screen.getAllByTestId("proof-copy");
    expect(copies).toHaveLength(4);
    expect(text(copies[0]!)).toContain("starkbank-ecdsa 2.0.0: starkbank-ecdsa-2.0.0.tar.gz, from PyPI");
    expect(text(copies[0]!)).toContain("the same as the registry's own");
    expect(text(copies[0]!)).toContain("Published on 8 October 2021.");
    expect(text(screen.getByTestId("proof-left-out"))).toContain("starkbank-ecdsa 1.1.1 was left out before the trial was registered");
    expect(text(screen.getByTestId("proof-copies"))).toContain("The first fetch of a version trusts the registry.");
  });
});

describe("a proposal with its proof", () => {
  it("shows the proof folded under its summary, and sends nothing until a button is pressed", () => {
    const fetchMock = mockApi({});
    render(<ProposalCard planId={7} proposal={withProof()} onDecided={() => {}} />);
    const card = screen.getByTestId("otto-proposal");
    expect((within(card).getByTestId("proof-block") as HTMLDetailsElement).open).toBe(false);
    expect(text(screen.getByTestId("proposal-status"))).toContain("Proposed");
    fireEvent.click(within(card).getByTestId("asking-code-toggle"));
    expect(calls(fetchMock)).toEqual([]);
  });

  it("a proposal without a proof draws no such block", () => {
    render(<ProposalCard planId={7} proposal={proposal()} onDecided={() => {}} />);
    expect(screen.queryByTestId("proof-block")).toBeNull();
  });

  it("Accept records the decision through the decide route, and nothing else is sent", async () => {
    const fetchMock = mockApi({ [route("accept")]: { body: acceptedProposal({ proof: proof() }) } });
    const decided = vi.fn();
    render(<ProposalCard planId={7} proposal={withProof()} onDecided={decided} />);
    fireEvent.click(screen.getByTestId("proposal-accept"));
    await waitFor(() => expect(decided).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([route("accept")]);
    expect(decided.mock.calls[0]?.[0].proof.title).toBe("How this test was proven");
  });

  it("Reject takes an optional short reason, and Cancel records nothing", async () => {
    const fetchMock = mockApi({ [route("reject")]: { body: rejectedProposal("We do not use this library in production") } });
    const decided = vi.fn();
    render(<ProposalCard planId={7} proposal={withProof()} onDecided={decided} />);
    fireEvent.click(screen.getByTestId("proposal-reject"));
    fireEvent.click(within(screen.getByTestId("proposal-reject-dialog")).getByTestId("proposal-reject-cancel"));
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.click(screen.getByTestId("proposal-reject"));
    fireEvent.change(screen.getByTestId("proposal-reject-reason"), { target: { value: "We do not use this library in production" } });
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(decided).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([route("reject")]);
  });

  it("an accepted proposal keeps its proof and can be undone until it has run", async () => {
    const fetchMock = mockApi({ [route("undo")]: { body: withProof() } });
    const decided = vi.fn();
    render(<ProposalCard planId={7} proposal={acceptedProposal({ proof: proof() })} onDecided={decided} />);
    expect(screen.getByTestId("proof-block")).toBeTruthy();
    fireEvent.click(screen.getByTestId("proposal-undo"));
    await waitFor(() => expect(decided).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([route("undo")]);
  });
});
