import type { TestProofBlock } from "../api";

/** Sandbox research: "How this test was proven", exactly as the backend words it for the test pack of one real run
 * (backend/tests/sandbox/fixtures/pack-2026.11.3.json: CVE-2021-43572 in starkbank-ecdsa). Made by
 * backend/app/present/proof.py from that pack; only the list of frozen files is cut to three. Every word here stands in
 * for the backend's; a test changes only what it is about. */
export const proofBlock: TestProofBlock = {
  "title": "How this test was proven",
  "label": "Sandbox copy",
  "summary": "Tried on public copies of starkbank-ecdsa fetched from PyPI: starkbank-ecdsa 2.0.0 got 1 of 64 cases wrong, starkbank-ecdsa 2.0.1 got none wrong, and the control that must fail did.",
  "table": {
    "columns": [
      "On public copies",
      "The reviewer's count",
      "What had to happen"
    ],
    "rows": [
      {
        "key": "reference",
        "label": "Our reference library, on the same cases",
        "count": "All 64 cases right",
        "must": "Every case right (the baseline)"
      },
      {
        "key": "affected",
        "label": "starkbank-ecdsa 2.0.0 (the version the advisory names as affected)",
        "count": "1 of 64 cases wrong",
        "must": "At least one case wrong"
      },
      {
        "key": "fixed",
        "label": "starkbank-ecdsa 2.0.1 (the publisher's fixed version)",
        "count": "All 64 cases right",
        "must": "As many right as our reference library"
      },
      {
        "key": "control",
        "label": "The control, a signer that accepts everything",
        "count": "64 of 64 cases wrong",
        "must": "Wrong on every case that must be refused"
      },
      {
        "key": "more-fixed-1",
        "label": "starkbank-ecdsa 2.0.2 (a further version after the fix)",
        "count": "All 64 cases right",
        "must": "As many right as our reference library"
      },
      {
        "key": "more-fixed-2",
        "label": "starkbank-ecdsa 2.3.1 (a further version after the fix)",
        "count": "All 64 cases right",
        "must": "As many right as our reference library"
      }
    ],
    "note": "Each count is the separate reviewer's, from the review of a run in a locked container on this computer. The right answers are the publisher's (Project Wycheproof, pinned by SHA-256); they never reach the code that asks the library."
  },
  "registered": {
    "line": "Registered in Otto's harness on 22 November 2026, 09:26 UTC, before the first run: the cases, the code, the copies, the images and what had to happen were frozen by fingerprint. A file that changes after that stops the trial. In the research ledger, a hash chain, the registration is entry 13 and the first run is entry 14.",
    "pins_title": "What was frozen, by SHA-256",
    "pins": [
      {
        "name": "designs/CVE-2021-43572-8fd946ef2a4d.json",
        "sha256": "c9934e49804fb161b18c14521b01d372a8c7b21470957df19695210b8c89c67c"
      },
      {
        "name": "qualify.py",
        "sha256": "14c5d54231e6fe2692c2a315ae59c29e21fc48bb3f659e11cbb58e51b8698579"
      },
      {
        "name": "sandbox/CVE-2021-43572/arms-d894ff4508c3.json",
        "sha256": "9a811f9a9877b6eddb8e295f134fc1430e9153f5b1145b0c587ec8d7fa3a313a"
      }
    ]
  },
  "judged": "Otto's harness judged the trial against those frozen thresholds: supported. One run for each part; nothing was run again to get a better draw.",
  "code": {
    "title": "The code that asked the library",
    "label": "Written by Otto",
    "author": "Claude (author a)",
    "file": "asking_code.py",
    "lines": 12,
    "source": "\"\"\"Asking code for starkbank-ecdsa: it passes one question to the library's own functions and hands its answer back.\"\"\"\nfrom ellipticcurve.curve import prime256v1\nfrom ellipticcurve.ecdsa import Ecdsa\nfrom ellipticcurve.publicKey import PublicKey\nfrom ellipticcurve.signature import Signature\n\nOWN_REFUSALS = ()\n\n\ndef check_signature(public_key, message, signature):\n    key = PublicKey.fromString(public_key[1:].hex(), curve=prime256v1)\n    return Ecdsa.verify(message.decode(\"utf-8\"), Signature.fromDer(signature), key)\n",
    "sha256": "3078900cdf8d3a7399c77fa132b297aa487be387fb4cbc269dea03c55886cace",
    "line": "12 lines, written for this library by Claude as Otto's code author. It holds no cryptography and decides nothing: it passes one question to the library's own functions and hands the library's own answer back. It was let through only after a screen by fixed rules and the check below.",
    "show": "Show the code",
    "hide": "Hide the code",
    "second": {
      "title": "The second author's version",
      "author": "Claude (author b)",
      "lines": 11,
      "source": "\"\"\"Asking code for starkbank-ecdsa (second author): one question, passed on to the library, and its own answer back.\"\"\"\nfrom ellipticcurve import Ecdsa, PublicKey, Signature\nfrom ellipticcurve.curve import p256\n\nOWN_REFUSALS = ()\n\n\ndef check_signature(public_key, message, signature):\n    point = PublicKey.fromString(\"00\" + public_key.hex(), curve=p256)\n    parsed = Signature.fromDer(signature)\n    return Ecdsa.verify(message=str(message, \"utf-8\"), signature=parsed, publicKey=point)\n",
      "sha256": "daa5b9de920827c88381d5a6cec1889cace2f061c2cc9f23d22addbb6345340c"
    },
    "agree_line": "Two versions of this code were written apart, by two authors that never saw each other's work. Asked the same cases, they gave the same answer on every case: 64 of 64 on starkbank-ecdsa 2.0.0 and 64 of 64 on starkbank-ecdsa 2.0.1.",
    "known_lines": [
      "Before the trial was registered, the code was checked on starkbank-ecdsa 2.0.1 with 24 fresh questions it had never seen: 12 signatures our reference library made, and 12 spoiled ones (the message changed by one character, or a signature made with another key). It had to hand back accept for the first and refuse for the second: 12 of 12 accepted, 12 of 12 refused.",
      "The questions were made from a random number drawn after the code was fixed, so they could not be known in advance.",
      "Two dummy pieces of code of ours, one that always says yes and one that always says no, went through the same check and were refused, as they must be.",
      "While it was a draft, the code ran on the fixed copy only. It never ran on the affected copy and never saw a result of the trial before it was fixed."
    ]
  },
  "copies": {
    "title": "The public copies",
    "rows": [
      {
        "version": "2.0.0",
        "role": "affected",
        "line": "starkbank-ecdsa 2.0.0: starkbank-ecdsa-2.0.0.tar.gz, from PyPI (read from recorded registry answers on this computer), fetched on 22 November 2026. SHA-256 71dec991bf6f5bf8…, the same as the registry's own.",
        "published": "8 October 2021",
        "helpers_line": null,
        "sha256": "71dec991bf6f5bf80cb0a57141ca69aae87e12a0385105feca87e26e7efa3681",
        "url": "https://files.pythonhosted.org/packages/2e/95/5c3453352eb01a8a0293ec6813e1c4318b62a853599e5e852b62d9a387dc/starkbank-ecdsa-2.0.0.tar.gz"
      },
      {
        "version": "2.0.1",
        "role": "fixed",
        "line": "starkbank-ecdsa 2.0.1: starkbank-ecdsa-2.0.1.tar.gz, from PyPI (read from recorded registry answers on this computer), fetched on 22 November 2026. SHA-256 fe7e36b580da097c…, the same as the registry's own.",
        "published": "4 November 2021",
        "helpers_line": null,
        "sha256": "fe7e36b580da097cc8c0a120e3b7ba335e3901b970a484fd5ce856c026ef7714",
        "url": "https://files.pythonhosted.org/packages/bf/03/e62f16fe4b5b565859d0d6b06a7b7b4b762a02d185e9e71baaa954ba14eb/starkbank-ecdsa-2.0.1.tar.gz"
      },
      {
        "version": "2.0.2",
        "role": "more_fixed",
        "line": "starkbank-ecdsa 2.0.2: starkbank-ecdsa-2.0.2.tar.gz, from PyPI (read from recorded registry answers on this computer), fetched on 22 November 2026. SHA-256 4b60ebc493f024f2…, the same as the registry's own.",
        "published": "9 November 2021",
        "helpers_line": null,
        "sha256": "4b60ebc493f024f2891516a6c140fcc711c16999468c8594bc1097ca5aed759f",
        "url": "https://files.pythonhosted.org/packages/90/58/6fcffc262d2d90aba14878d22bf7d331a74f3190fdd79aa1df8700fd4f81/starkbank-ecdsa-2.0.2.tar.gz"
      },
      {
        "version": "2.3.1",
        "role": "more_fixed",
        "line": "starkbank-ecdsa 2.3.1: starkbank_ecdsa-2.3.1-py3-none-any.whl, from PyPI (read from recorded registry answers on this computer), fetched on 22 November 2026. SHA-256 c6dcb0caeb5d7d18…, the same as the registry's own.",
        "published": "23 April 2026",
        "helpers_line": null,
        "sha256": "c6dcb0caeb5d7d181c3ef0a6b0185df700d4fa5d5e5669b40bc6d20816aa25a8",
        "url": "https://files.pythonhosted.org/packages/68/f3/6d0a27fe51ba9cca11a1d5f44616ba384c1326ab704d74e4367839a67219/starkbank_ecdsa-2.3.1-py3-none-any.whl"
      }
    ],
    "left_out": [
      "starkbank-ecdsa 1.1.1 was left out before the trial was registered: the asking code does not work on it (it did not accept fresh signatures that a reference library made).",
      "starkbank-ecdsa 1.1.0 was left out before the trial was registered: the asking code does not work on it (it did not accept fresh signatures that a reference library made)."
    ],
    "image_line": "Built into one container image with no network (evidence-lab-sandbox-starkbank-ecdsa:c32a7fb9893fa38f). Nothing of a package ran while it was fetched or unpacked; a copy runs only in a locked container on this computer.",
    "trust_line": "The first fetch of a version trusts the registry. A later fetch that differs is refused."
  },
  "replayed": "Replayed in a separate step by a second author role of the same build, on this computer. Not by an outside party.",
  "not_shown": "What this does not show. It shows which published cases get a wrong answer on these public copies. It does not say how serious the weakness is, and it says nothing about any other system."
};

export function proof(over: Partial<TestProofBlock> = {}): TestProofBlock {
  return { ...structuredClone(proofBlock), ...over };
}
