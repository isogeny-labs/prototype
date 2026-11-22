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
      "Count",
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
    "note": "The counts for the library's copies and for our reference library are the separate reviewer's, from its review of a run in a locked container on this computer. The control's count is made by the pinned trial script, from the control's raw answers. The right answers are the publisher's (Project Wycheproof, pinned by SHA-256); they never reach the code that asks the library."
  },
  "registered": {
    "line": "Registered in Otto's harness on 22 November 2026, 11:27 UTC, before the first run: the cases, the code, the copies, the images and what had to happen were frozen by fingerprint. A file that changes after that stops the trial. In the research ledger, a hash chain, the registration is entry 13 and the first run is entry 14.",
    "pins_title": "What was frozen, by SHA-256",
    "pins": [
      {
        "name": "designs/CVE-2021-43572-8fd946ef2a4d.json",
        "sha256": "c9934e49804fb161b18c14521b01d372a8c7b21470957df19695210b8c89c67c"
      },
      {
        "name": "qualify.py",
        "sha256": "cc854f95ce2c135484835579b0ce33d5c401cd96e5dd37270968b2ab42d63b39"
      },
      {
        "name": "sandbox/CVE-2021-43572/arms-44ac0fa1e98c.json",
        "sha256": "e67c4fbb709494ea98016d4cb3f588366c1473b7d7616989430695ee50aade68"
      }
    ]
  },
  "judged": "Otto's harness judged the trial against those frozen thresholds: supported. One run for each part; nothing was run again to get a better draw.",
  "code": {
    "title": "The code that asked the library",
    "label": "Written by Otto",
    "author": "Recorded during the build, not through the API (author a)",
    "file": "asking_code.py",
    "lines": 11,
    "source": "from ellipticcurve.curve import prime256v1\nfrom ellipticcurve.ecdsa import Ecdsa\nfrom ellipticcurve.publicKey import PublicKey\nfrom ellipticcurve.signature import Signature\n\nOWN_REFUSALS = ()\n\n\ndef check_signature(public_key, message, signature):\n    key = PublicKey.fromString(public_key[1:].hex(), curve=prime256v1)\n    return Ecdsa.verify(message.decode(\"utf-8\"), Signature.fromDer(signature), key)\n",
    "sha256": "1cf463ed299f4340f974e16f2a36e7ea474fc60a63b1eafc6b665f9ff1083194",
    "line": "11 lines, written for this library during the build and recorded, not written through the API. Its one job is to pass a question to the library's own functions and hand the library's own answer back. It was let through only after a screen by fixed rules (straight-line calls into the library, and nothing else) and the check below. The screen is a filter for mistakes and plain tricks, not a proof, which is why a second version, written apart, had to give the same answer on every case.",
    "show": "Show the code",
    "hide": "Hide the code",
    "second": {
      "title": "The second author's version",
      "author": "Recorded during the build, not through the API (author b)",
      "lines": 11,
      "source": "from ellipticcurve import Ecdsa, PublicKey, Signature\nfrom ellipticcurve.curve import p256\n\nOWN_REFUSALS = ()\n\n\ndef check_signature(public_key, message, signature):\n    point = PublicKey.fromString(public_key[1:65].hex(), curve=p256)\n    parsed = Signature.fromDer(signature)\n    text = message.decode(\"utf-8\")\n    return Ecdsa.verify(message=text, signature=parsed, publicKey=point)\n",
      "sha256": "b307a3ae90d506f7a9c6b0a5f3caac5677da6b7ed2dca0888a464fc3003ee792"
    },
    "agree_line": "Two versions of this code were written apart during the build. They are recorded answers, not written through the API. Asked the same cases, they gave the same answer on every case: 64 of 64 on starkbank-ecdsa 2.0.0 and 64 of 64 on starkbank-ecdsa 2.0.1 (counted by the pinned trial script).",
    "known_lines": [
      "Before the trial was registered, the code was checked on starkbank-ecdsa 2.0.1 with 24 fresh questions it had never seen: 12 signatures our reference library made, and 12 spoiled ones (the message changed by one character, or a signature made with another key). It had to hand back accept for the first and refuse for the second: 12 of 12 accepted, 12 of 12 refused.",
      "The questions were made from a random number drawn after the code was fixed, so they could not be known in advance.",
      "Two dummy pieces of code of ours, one that always says yes and one that always says no, went through the same check on every copy. Each answered every question its one way, and the check refused both, as it must.",
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
    "image_line": "Built into one container image with no network (evidence-lab-sandbox-starkbank-ecdsa:12326fe0bbddb614). Nothing of a package ran while it was fetched or unpacked; a copy runs only in a locked container on this computer.",
    "trust_line": "The first fetch of a version trusts the registry. A later fetch that differs is refused."
  },
  "replayed": "Replayed in a separate step by a second author role of the same build, on this computer. Not by an outside party.",
  "not_shown": "What this does not show. It shows which published cases get a wrong answer on these public copies. It does not say how serious the weakness is, and it says nothing about any other system."
};

export function proof(over: Partial<TestProofBlock> = {}): TestProofBlock {
  return { ...structuredClone(proofBlock), ...over };
}
