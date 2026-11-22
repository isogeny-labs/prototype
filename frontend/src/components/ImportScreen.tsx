import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import {
  api,
  ApiError,
  errorMessage,
  MAX_UPLOAD_BYTES,
  type Address,
  type Claim,
  type ClaimKind,
  type DemoServer,
  type Import,
  type VerifyRun,
  type Source,
} from "../api";
import { CLOSED_SENTENCE, useReadOnly } from "../readOnly";
import { DataTable, DetailPanel, PageHeader, TableWithPanel, type Column } from "./layout";
import { FromOttoTag } from "./otto/ProposalCard";
import { AlgoName } from "./plainName";
import { ItemLinkView, RelatedFor } from "./related";
import { DemoDataLabel, ErrorBox, PrimaryButton, SecondaryButton, SourceTag, WhereFromTag } from "./ui";

const KIND_LABELS: Record<ClaimKind, string> = {
  protocol_versions: "TLS versions",
  cipher_suites: "Cipher suites",
  key_exchange: "Key exchange",
  certificate: "Certificate",
  signature_algorithm: "Signature algorithm",
  post_quantum: "Post-quantum status",
};

const LOCATION_LABELS: Record<Claim["location_kind"], string> = {
  server: "Server",
  software: "Software",
  unknown: "Unrecognised location",
};

/** 22 November 2026: every claim on this page is From your file (the import's tag, in the backend's words) until Verify
 * checks it. Where the import carries no tag (an older answer), the small "from the file" tag stays as it was. */
function FromFile({ tag }: { tag: Source | null | undefined }) {
  return tag ? <WhereFromTag tag={tag} /> : <SourceTag>from the file</SourceTag>;
}

const claimColumns = (tag: Source | null | undefined): Column<Claim>[] => [
  {
    key: "where",
    header: "Where",
    render: (claim) => (
      <>
        <div className="font-mono text-slate-100">{claim.location}</div>
        <div className="mt-0.5 text-xs text-slate-500">{LOCATION_LABELS[claim.location_kind]}</div>
      </>
    ),
  },
  {
    key: "what",
    header: "What",
    render: (claim) => (
      <>
        <div className="text-slate-100">{KIND_LABELS[claim.kind]}</div>
        <div className="mt-0.5 text-xs text-slate-400">{claim.text}</div>
      </>
    ),
  },
  {
    key: "value",
    header: "Claimed value",
    render: (claim) => (
      <>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-slate-100">
            <AlgoName text={claim.claimed_value} />
          </span>
          <FromFile tag={tag} />
        </div>
        <div className="mt-0.5 text-xs text-slate-500">{claim.source}</div>
      </>
    ),
  },
];

// Phase 5b: beside the open panel, a row is where and what, and the claimed value.
const compactClaimColumns: Column<Claim>[] = [
  {
    key: "where",
    header: "Where and what",
    minWidth: 160,
    render: (claim) => (
      <>
        <div className="font-mono text-slate-100">{claim.location}</div>
        <div className="mt-0.5 text-xs text-slate-400">{KIND_LABELS[claim.kind]}</div>
      </>
    ),
  },
  {
    key: "value",
    header: "Claimed value",
    minWidth: 110,
    render: (claim) => (
      <span className="font-medium text-slate-100">
        <AlgoName text={claim.claimed_value} />
      </span>
    ),
  },
];

/** What opens in the panel: the claim as the file states it, and where in the file it was read. */
function ClaimDetails({ claim, tag }: { claim: Claim; tag: Source | null | undefined }) {
  return (
    <dl data-testid="claim-details" className="space-y-4 text-sm">
      <div>
        <dt className="text-xs uppercase tracking-wide text-slate-500">Where</dt>
        <dd className="mt-1 font-mono text-slate-100">{claim.location}</dd>
        <dd className="text-xs text-slate-400">{LOCATION_LABELS[claim.location_kind]}</dd>
      </div>
      <div>
        <dt className="text-xs uppercase tracking-wide text-slate-500">What</dt>
        <dd className="mt-1 text-slate-100">{KIND_LABELS[claim.kind]}</dd>
        <dd className="text-xs text-slate-400">{claim.text}</dd>
      </div>
      <div>
        <dt className="text-xs uppercase tracking-wide text-slate-500">Claimed value</dt>
        <dd className="mt-1 flex flex-wrap items-center gap-2 text-slate-100">
          <span className="font-medium">{claim.claimed_value}</span>
          <FromFile tag={tag} />
        </dd>
        {/* 22 November 2026: what the tag means for this claim, in the backend's sentence */}
        {tag?.note ? (
          <dd data-testid="source-note" className="mt-1 text-xs text-slate-400">
            {tag.note}
          </dd>
        ) : null}
      </div>
      <div>
        <dt className="text-xs uppercase tracking-wide text-slate-500">Source in the file</dt>
        <dd className="mt-1 text-slate-300">{claim.source}</dd>
      </div>
    </dl>
  );
}

interface UploadError {
  message: string;
  line: number | null;
  field: string | null;
}

interface Props {
  demoServer: DemoServer;
  imp: Import | null;
  onImported: (imp: Import) => void;
  /** A file upload failed: the previous file's claims must go, so only the error shows. */
  onImportFailed: () => void;
  onAddressChanged: (address: Address) => void;
  onVerified: (run: VerifyRun) => void;
  /** Phase 5a: the assessment the next file goes into. The app starts a new assessment first when this one already
   * has a file, so each file brought in gets its own assessment. */
  target?: () => Promise<number | undefined>;
  /** Phase 5a: one plain sentence above the drop zone (for example that another file starts a new assessment). */
  targetNote?: string | null;
  /** Phase 5b: a claim to open (from a link: #/a/<id>/inventory/import?item=claim-<id>). */
  openItem?: string | null;
}

export function ImportScreen({ demoServer, imp, onImported, onImportFailed, onAddressChanged, onVerified, target, targetNote, openItem = null }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const closed = useReadOnly();
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadError, setUploadError] = useState<UploadError | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [addressBusy, setAddressBusy] = useState<string | null>(null);
  const [addressError, setAddressError] = useState<string | null>(null);
  // The claim whose panel is open, for the file it belongs to (a new file starts with none open).
  const [opened, setOpened] = useState<{ file: number; claim: number } | null>(null);
  const linked = openItem && openItem.startsWith("claim-") ? Number(openItem.slice(6)) : null;
  // A link to a claim opens it when the link or the file changes. Not each time the file's data is read again (an
  // address ticked, Otto's line refreshed): a panel the person has closed stays closed.
  const fileId = imp?.id ?? null;
  useEffect(() => {
    if (linked !== null && fileId !== null) setOpened({ file: fileId, claim: linked });
  }, [linked, fileId]);
  const openClaim = imp && opened?.file === imp.id ? (imp.claims.find((c) => c.id === opened.claim) ?? null) : null;
  const closeClaim = useCallback(() => setOpened(null), []);

  async function load(action: (assessmentId?: number) => Promise<Import>, isUpload = false) {
    setUploadError(null);
    setVerifyError(null);
    setAddressError(null);
    setLoading(true);
    try {
      const assessmentId = target ? await target() : undefined;
      onImported(await action(assessmentId));
    } catch (e) {
      if (isUpload) onImportFailed();
      setUploadError({
        message: errorMessage(e),
        line: e instanceof ApiError ? e.line : null,
        field: e instanceof ApiError ? e.field : null,
      });
    } finally {
      setLoading(false);
    }
  }

  // A file refused here never reaches the server, so tell the server too (with an empty body it will
  // reject): otherwise a page refresh would bring the previous file's claims back.
  function refuseLocally(file: File) {
    void (async () => {
      const assessmentId = target ? await target().catch(() => undefined) : undefined;
      onImportFailed();
      void api.importFile(new File([], file.name), assessmentId).catch(() => undefined);
    })();
  }

  function uploadFile(file: File) {
    const name = file.name.toLowerCase();
    if (!name.endsWith(".json") && !name.endsWith(".csv")) {
      refuseLocally(file);
      setUploadError({
        message: `"${file.name}" isn't a .json or .csv file. Choose a CycloneDX CBOM (.json) or our CSV template (.csv).`,
        line: null,
        field: null,
      });
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      refuseLocally(file);
      setUploadError({ message: `"${file.name}" is larger than 1 MB, which is the most this app reads.`, line: null, field: null });
      return;
    }
    void load((assessmentId) => api.importFile(file, assessmentId), true);
  }

  function onFileChosen(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) uploadFile(file);
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  }

  async function toggleAddress(address: Address, confirmed: boolean) {
    if (!imp) return;
    setAddressError(null);
    setAddressBusy(address.address);
    try {
      onAddressChanged(await api.confirmAddress(imp.id, address.address, confirmed));
    } catch (e) {
      setAddressError(`Couldn't save your answer for ${address.address}: ${errorMessage(e)}`);
    } finally {
      setAddressBusy(null);
    }
  }

  async function verify() {
    if (!imp) return;
    setVerifyError(null);
    setVerifying(true);
    try {
      onVerified(await api.verify(imp.id));
    } catch (e) {
      setVerifyError(errorMessage(e));
      setVerifying(false);
    }
  }

  // Many messages already say "Line 3: ..." or "... on line 3"; don't repeat the line under them.
  const showLine =
    uploadError !== null &&
    uploadError.line !== null &&
    !new RegExp(`\\bline ${uploadError.line}\\b`, "i").test(uploadError.message);

  // Nothing is contacted until the user has ticked every address we could look up.
  const waitingForTicks = imp ? imp.addresses.some((a) => !a.confirmed && !a.error) : false;

  const skipped = imp?.skipped ?? [];
  // Settings rows are not claims: nothing checks them. Older stored answers may not have them.
  const settings = imp?.settings ?? [];
  // Only the upload reply carries these (for example: the demo test servers this file needs were started).
  const notices = imp?.notices ?? [];
  // Phase 5c: how many checks of the installed test packs may apply to this file, in the backend's words, with the
  // way to Advisories. A line and a link: bringing a file in adds nothing and runs nothing.
  const otto = imp?.otto ?? null;

  return (
    <section aria-label="Import" className="space-y-6">
      <PageHeader
        eyebrow="Inventory"
        title="Import"
        description="Bring in the file from your scanning tool that lists where encryption is used and how. We read it as data only; nothing in it is run."
      />

      {targetNote ? (
        <p data-testid="import-target-note" className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-2.5 text-sm text-slate-300">
          {targetNote}
        </p>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex flex-1 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors focus-within:border-sky-400 ${
            dragging ? "border-sky-400 bg-sky-400/10" : "border-slate-700 bg-slate-900/50 hover:border-slate-500"
          }`}
        >
          <span className="text-sm font-medium text-slate-100">Drop a file here, or click to choose one</span>
          <span className="mt-1 text-xs text-slate-400">CycloneDX CBOM (.json) or our CSV template (.csv), up to 1 MB</span>
          <input
            ref={fileInput}
            type="file"
            accept=".json,.csv,application/json,text/csv"
            aria-label="Choose a file to import"
            onChange={onFileChosen}
            disabled={loading || verifying || closed}
            className="sr-only"
          />
        </label>
        <div className="flex items-center justify-center sm:px-2">
          <SecondaryButton onClick={() => void load((assessmentId) => api.importDemo(assessmentId))} disabled={loading || verifying}>
            Use demo file
          </SecondaryButton>
        </div>
      </div>

      {loading ? (
        <p role="status" className="text-sm text-slate-400">
          Reading the file…
        </p>
      ) : null}

      {uploadError ? (
        <ErrorBox title="We couldn't read that file">
          <p>{uploadError.message}</p>
          {showLine || uploadError.field !== null ? (
            <p className="mt-1 text-amber-200/90">
              {showLine ? <span>Line {uploadError.line}</span> : null}
              {showLine && uploadError.field !== null ? <span> · </span> : null}
              {uploadError.field !== null ? (
                <span>
                  Field: <code className="font-mono">{uploadError.field}</code>
                </span>
              ) : null}
            </p>
          ) : null}
        </ErrorBox>
      ) : null}

      {imp ? (
        <>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <h2 className="text-base font-semibold text-slate-100">What the file claims</h2>
              {imp.is_demo ? <DemoDataLabel /> : null}
              <span className="text-xs text-slate-500">
                {imp.filename} · {imp.format === "csv" ? "CSV template" : "CycloneDX CBOM"}
              </span>
            </div>
            {imp.claims.length === 0 ? (
              <p className="text-sm text-slate-400">This file has no encryption claims we can check.</p>
            ) : (
              <TableWithPanel
                panelOpen={openClaim !== null}
                table={
                  <DataTable
                    label="What the file claims"
                    columns={claimColumns(imp?.claim_source_tag)}
                    compactColumns={compactClaimColumns}
                    rows={imp.claims}
                    rowKey={(claim) => String(claim.id)}
                    rowTestId="claim-row"
                    selectedKey={openClaim ? String(openClaim.id) : null}
                    onRowClick={(claim) => setOpened((cur) => (cur?.claim === claim.id && cur.file === imp.id ? null : { file: imp.id, claim: claim.id }))}
                  />
                }
                panel={
                  <DetailPanel
                    open={openClaim !== null}
                    item={openClaim ? `claim-${openClaim.id}` : null}
                    title={openClaim ? openClaim.location : ""}
                    subtitle={openClaim ? LOCATION_LABELS[openClaim.location_kind] : undefined}
                    onClose={closeClaim}
                    testId="claim-panel"
                  >
                    {openClaim ? (
                      <p className="mb-3 text-sm">
                        <ItemLinkView link={{ page: "inventory/verify", item: `claim-${openClaim.id}` }} testId="claim-to-verify">
                          Its Verify result
                        </ItemLinkView>
                      </p>
                    ) : null}
                    {openClaim ? (
                      <>
                        <ClaimDetails claim={openClaim} tag={imp?.claim_source_tag} />
                        <RelatedFor itemKey={`claim:${openClaim.id}`} />
                      </>
                    ) : null}
                  </DetailPanel>
                }
              />
            )}
            {otto ? (
              <div data-testid="import-otto" data-count={otto.count} className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm">
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-slate-200">
                  <FromOttoTag label={otto.label} testId="import-otto-label" />
                  <span data-testid="import-otto-text" className="min-w-0 break-words">
                    {otto.text}
                  </span>
                </p>
                <p className="mt-1.5 break-words text-xs text-slate-400">
                  <span data-testid="import-otto-note">{otto.note}</span>{" "}
                  <ItemLinkView link={otto.link} testId="import-otto-link">
                    {otto.link_label}
                  </ItemLinkView>
                </p>
              </div>
            ) : null}
            {settings.length > 0 ? (
              <div data-testid="import-settings" className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
                <h3 className="text-sm font-semibold text-slate-100">{imp.settings_title}</h3>
                <ul className="mt-1.5 space-y-1 text-sm">
                  {settings.map((setting, i) => (
                    <li key={i} data-testid="import-setting">
                      <span className="font-mono text-slate-100">{setting.location}</span>
                      <span className="text-slate-300"> {setting.text}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {notices.length > 0 ? (
              <div className="space-y-1.5">
                {notices.map((notice, i) => (
                  <p
                    key={i}
                    data-testid="import-notice"
                    className="rounded-md border border-slate-700 bg-slate-900/60 px-3 py-2 text-[13px] text-slate-300"
                  >
                    {notice}
                  </p>
                ))}
              </div>
            ) : null}
            {skipped.length > 0 ? (
              <details data-testid="skipped-note" className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-2.5 text-sm">
                <summary className="cursor-pointer text-slate-300">
                  {skipped.length === 1 ? "1 item skipped" : `${skipped.length} items skipped`}: not checked in this version
                </summary>
                <ul className="mt-2 space-y-2">
                  {skipped.map((item, i) => (
                    <li key={i} data-testid="skipped-item">
                      <div className="text-slate-100">
                        <span className="font-medium">{item.name}</span>
                        <span className="text-slate-400"> · {item.what}</span>
                      </div>
                      <div className="text-xs text-slate-400">{item.reason}</div>
                      <div className="text-xs text-slate-500">{item.source}</div>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>

          {!demoServer.running && (imp.is_demo || imp.addresses.some((x) => x.address === demoServer.address)) ? (
            <ErrorBox title={`The demo server at ${demoServer.address} isn't running`}>
              <p>{demoServer.error ?? "No reason was given."}</p>
              <p className="mt-1">Claims about that address will come back as Couldn't check.</p>
            </ErrorBox>
          ) : null}

          {imp.addresses.length > 0 ? (
            <fieldset className="space-y-2 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <legend className="px-1 text-sm font-semibold text-slate-100">Before we contact anything</legend>
              <p className="text-sm text-slate-400">
                Checking a server means connecting to it (handshakes only, no attacks, no load). Tick each address you
                want checked.
              </p>
              <ul className="space-y-2 pt-1">
                {imp.addresses.map((address) => (
                  <li key={address.address}>
                    <label className="flex cursor-pointer items-start gap-3 text-sm">
                      <input
                        type="checkbox"
                        data-testid="address-confirm"
                        checked={address.confirmed}
                        disabled={addressBusy === address.address || verifying || closed}
                        title={closed ? CLOSED_SENTENCE : undefined}
                        onChange={(e) => void toggleAddress(address, e.target.checked)}
                        className="mt-0.5 h-4 w-4 accent-sky-400"
                      />
                      <span>
                        <span className="text-slate-100">I own this system or am allowed to test it</span>
                        <span className="block text-xs text-slate-400">
                          <span className="font-mono text-slate-300">{address.address}</span>
                          {address.resolved_ip ? (
                            <>
                              {" "}
                              (connects to <span className="font-mono text-slate-300">{address.resolved_ip}</span>
                              {address.is_loopback ? ", this computer" : ""})
                            </>
                          ) : null}
                        </span>
                      </span>
                    </label>
                    {address.error ? (
                      <p role="alert" className="ml-7 mt-1 text-xs text-amber-200">
                        {address.error}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
              {addressError ? <ErrorBox>{addressError}</ErrorBox> : null}
            </fieldset>
          ) : null}

          {verifyError ? <ErrorBox title="The check didn't finish">{verifyError}</ErrorBox> : null}

          <div className="flex flex-wrap items-center gap-4">
            <PrimaryButton onClick={() => void verify()} busy={verifying} disabled={waitingForTicks || loading}>
              Verify claims
            </PrimaryButton>
            {verifying ? (
              <p role="status" className="text-sm text-slate-300">
                Checking each claim against the real system. This takes a few seconds…
              </p>
            ) : waitingForTicks ? (
              <p className="text-sm text-slate-400">Tick the box for each address above first.</p>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
