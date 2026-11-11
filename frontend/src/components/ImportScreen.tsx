import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
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
} from "../api";
import { DemoDataLabel, ErrorBox, PrimaryButton, SecondaryButton, SourceTag } from "./ui";

const KIND_LABELS: Record<ClaimKind, string> = {
  protocol_versions: "TLS versions",
  cipher_suites: "Cipher suites",
  key_exchange: "Key exchange",
  certificate: "Certificate",
  signature_algorithm: "Signature algorithm",
};

const LOCATION_LABELS: Record<Claim["location_kind"], string> = {
  server: "Server",
  software: "Software",
  unknown: "Unrecognised location",
};

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
}

export function ImportScreen({ demoServer, imp, onImported, onImportFailed, onAddressChanged, onVerified }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadError, setUploadError] = useState<UploadError | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [addressBusy, setAddressBusy] = useState<string | null>(null);
  const [addressError, setAddressError] = useState<string | null>(null);

  async function load(action: () => Promise<Import>, isUpload = false) {
    setUploadError(null);
    setVerifyError(null);
    setAddressError(null);
    setLoading(true);
    try {
      onImported(await action());
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
    onImportFailed();
    void api.importFile(new File([], file.name)).catch(() => undefined);
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
    void load(() => api.importFile(file), true);
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

  return (
    <section aria-labelledby="import-title" className="space-y-6">
      <div>
        <h1 id="import-title" className="text-xl font-semibold text-slate-50">
          Import
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Bring in the file from your scanning tool that lists where encryption is used and how. We read it as data only;
          nothing in it is run.
        </p>
      </div>

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
            disabled={loading || verifying}
            className="sr-only"
          />
        </label>
        <div className="flex items-center justify-center sm:px-2">
          <SecondaryButton onClick={() => void load(api.importDemo)} disabled={loading || verifying}>
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
              <div className="overflow-x-auto rounded-xl border border-slate-800">
                <table className="w-full min-w-[36rem] text-left text-sm">
                  <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
                    <tr>
                      <th scope="col" className="px-4 py-2.5 font-medium">
                        Where
                      </th>
                      <th scope="col" className="px-4 py-2.5 font-medium">
                        What
                      </th>
                      <th scope="col" className="px-4 py-2.5 font-medium">
                        Claimed value
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {imp.claims.map((claim) => (
                      <tr key={claim.id} data-testid="claim-row" className="align-top">
                        <td className="px-4 py-3">
                          <div className="font-mono text-slate-100">{claim.location}</div>
                          <div className="mt-0.5 text-xs text-slate-500">{LOCATION_LABELS[claim.location_kind]}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-slate-100">{KIND_LABELS[claim.kind]}</div>
                          <div className="mt-0.5 text-xs text-slate-400">{claim.text}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-slate-100">{claim.claimed_value}</span>
                            <SourceTag>from the file</SourceTag>
                          </div>
                          <div className="mt-0.5 text-xs text-slate-500">{claim.source}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
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
                        disabled={addressBusy === address.address || verifying}
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
