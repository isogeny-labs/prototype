import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProposalCard } from "../components/otto/ProposalCard";
import { ReadOnlyProvider } from "../readOnly";
import { calls, mockApi, text } from "./fixtures";
import { acceptedProposal, proposal, rejectedProposal } from "./proposalFixtures";

/** Phase 5c: Otto proposes; a person decides. The card is the same on every tab that shows a proposal. */

const ID = "check-cve-2022-21449-f3ea2161c217";
const route = (decision: string) => `POST /api/plans/7/otto/proposals/${ID}/${decision}`;

/** What one request sent as its JSON body. */
function sent(fetchMock: ReturnType<typeof mockApi>, n = 0): unknown {
  const init = fetchMock.mock.calls[n]?.[1];
  return init?.body ? JSON.parse(String(init.body)) : null;
}

describe("one of Otto's proposals", () => {
  it("says it is from Otto, why it applies and that nobody has decided, and sends nothing until a button is pressed", () => {
    const fetchMock = mockApi({});
    render(<ProposalCard planId={7} proposal={proposal()} onDecided={() => {}} />);
    expect(text(screen.getByTestId("proposal-label"))).toContain("From Otto");
    expect(text(screen.getByTestId("proposal-status"))).toContain("Proposed");
    expect(text(screen.getByTestId("proposal-why"))).toContain("Why it applies");
    expect(text(screen.getByTestId("proposal-decided"))).toContain("Nobody has decided this yet.");
    expect(text(screen.getByTestId("proposal-note"))).toContain("It runs nothing.");
    expect(calls(fetchMock)).toEqual([]);
  });

  it("Accept records the decision through the decide route and hands back the proposal as it now stands", async () => {
    const fetchMock = mockApi({ [route("accept")]: { body: acceptedProposal() } });
    const decided = vi.fn();
    render(<ProposalCard planId={7} proposal={proposal()} onDecided={decided} />);
    fireEvent.click(screen.getByTestId("proposal-accept"));
    await waitFor(() => expect(decided).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([route("accept")]);
    expect(sent(fetchMock)).toEqual({});
    expect(decided.mock.calls[0]?.[0].status.word).toBe("Added");
  });

  it("Reject asks for an optional short reason, and Cancel records nothing", async () => {
    const fetchMock = mockApi({ [route("reject")]: { body: rejectedProposal("Not this quarter") } });
    const decided = vi.fn();
    render(<ProposalCard planId={7} proposal={proposal()} onDecided={decided} />);
    fireEvent.click(screen.getByTestId("proposal-reject"));
    const box = screen.getByTestId("proposal-reject-dialog");
    expect(text(box)).toContain("It is not deleted");
    fireEvent.click(within(box).getByTestId("proposal-reject-cancel"));
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    expect(calls(fetchMock)).toEqual([]);

    fireEvent.click(screen.getByTestId("proposal-reject"));
    fireEvent.change(screen.getByTestId("proposal-reject-reason"), { target: { value: "Not this quarter" } });
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(decided).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([route("reject")]);
    expect(sent(fetchMock)).toEqual({ reason: "Not this quarter" });
    expect(decided.mock.calls[0]?.[0].status.word).toBe("Not added (Not this quarter)");
  });

  it("a reject with no reason sends none", async () => {
    const fetchMock = mockApi({ [route("reject")]: { body: rejectedProposal("") } });
    render(<ProposalCard planId={7} proposal={proposal()} onDecided={() => {}} />);
    fireEvent.click(screen.getByTestId("proposal-reject"));
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(calls(fetchMock)).toEqual([route("reject")]));
    expect(sent(fetchMock)).toEqual({});
  });

  it("an accepted proposal shows who decided and when, and Undo", async () => {
    const fetchMock = mockApi({ [route("undo")]: { body: proposal() } });
    const decided = vi.fn();
    render(<ProposalCard planId={7} proposal={acceptedProposal()} onDecided={decided} />);
    expect(text(screen.getByTestId("proposal-status"))).toContain("Added");
    expect(text(screen.getByTestId("proposal-decided"))).toContain("Accepted by You on 18 November 2026, 10:02 UTC.");
    expect(text(screen.getByTestId("proposal-decision"))).toContain("1. Accepted by You");
    expect(screen.queryByTestId("proposal-accept")).toBeNull();
    fireEvent.click(screen.getByTestId("proposal-undo"));
    await waitFor(() => expect(decided).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([route("undo")]);
  });

  it("a rejected proposal stays, as Not added with its reason, and can be taken up again", async () => {
    const fetchMock = mockApi({ [route("reconsider")]: { body: proposal() } });
    const decided = vi.fn();
    render(<ProposalCard planId={7} proposal={rejectedProposal("Not this quarter")} onDecided={decided} />);
    expect(text(screen.getByTestId("proposal-status"))).toContain("Not added (Not this quarter)");
    expect(text(screen.getByTestId("proposal-decided"))).toContain("Reason: Not this quarter");
    expect(screen.queryByTestId("proposal-accept")).toBeNull();
    fireEvent.click(screen.getByTestId("proposal-reconsider"));
    await waitFor(() => expect(decided).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([route("reconsider")]);
  });

  it("a button the backend would refuse is off and says why", () => {
    const locked = acceptedProposal({
      buttons: [{ key: "undo", label: "Undo", can: false, blocked_reason: "This check has run, so it stays in the test plan." }],
      note: null,
    });
    mockApi({});
    render(<ProposalCard planId={7} proposal={locked} onDecided={() => {}} />);
    expect((screen.getByTestId("proposal-undo") as HTMLButtonElement).disabled).toBe(true);
    expect(text(screen.getByTestId("proposal-blocked"))).toContain("This check has run, so it stays in the test plan.");
  });

  it("a refusal from the backend is shown in its own words, and nothing is handed back", async () => {
    mockApi({
      [route("accept")]: { status: 409, body: { error: { message: "This assessment is closed. Start a new one to continue.", line: null, field: null } } },
    });
    const decided = vi.fn();
    render(<ProposalCard planId={7} proposal={proposal()} onDecided={decided} />);
    fireEvent.click(screen.getByTestId("proposal-accept"));
    expect(text(await screen.findByText("This assessment is closed. Start a new one to continue."))).toContain("closed");
    expect(decided).not.toHaveBeenCalled();
  });

  it("in a closed assessment every decision button is off", () => {
    mockApi({});
    render(
      <ReadOnlyProvider readOnly>
        <ProposalCard planId={7} proposal={proposal()} onDecided={() => {}} />
      </ReadOnlyProvider>,
    );
    expect((screen.getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("proposal-reject") as HTMLButtonElement).disabled).toBe(true);
  });
});
