# CSfC priorities: where Isogeny Labs fits

Status: strategy note, 2026-11-15. Not a product commitment and not part of the tested scope in `SCOPE.md`.

Evidence standing: the NSA Components List page returned HTTP 403 to the session that wrote this note, so it was not
read directly. The dates below come from search summaries of NSA's 2026 CSfC selection documents and from atsec's
reporting. **Check them against the current selection documents before committing money or schedule to them.**

## The position

The [CSfC Components List](https://www.nsa.gov/Resources/Commercial-Solutions-for-Classified-Program/components-list/)
lists finished products: IPsec VPN gateways and clients, MACsec devices, TLS applications, and similar. Each one is
NIAP-evaluated first and then goes through a separate CSfC approval step. A crypto library cannot be listed.

So the list is not our target. The vendors on it are our customers.

## Why now

- NSA's 2026 selection documents say that in 2027 new Components List entries must, where applicable, use
  ML-KEM-1024, ML-DSA-87, LMS and/or XMSS.
- atsec reports that NIAP will stop accepting evaluations that are not fully CNSA 2.0 from 2028-01-01.

Every listed vendor has to retrofit on that schedule, and each of them needs evidence that the retrofit is correct.

## Priorities, in order

1. **Evidence Lab for CNSA 2.0 retrofits.** This repository already imports an implementation, runs reproducible
   tests, and exports signed evidence. Point it at vendors heading into NIAP evaluation. It brings revenue and
   relationships before any module of our own is validated.
2. **The CNSA 2.0 suite and nothing else.** ML-KEM-1024, ML-DSA-87, LMS/XMSS verification, AES-256, SHA-384/512.
   Leave LMS/XMSS signing alone: it needs stateful HSM handling. Isogeny schemes are not in CNSA 2.0 and earn
   nothing here.
3. **Assurance as the differentiator.** The basic algorithms are free in OpenSSL 3.5, AWS-LC, wolfCrypt and liboqs,
   so correctness alone will not sell. What could:
   - constant-time code with evidence;
   - side-channel-hardened (masked) ML-DSA and ML-KEM for appliances;
   - machine-checked proofs (the Lean work in the sibling repositories carries over);
   - `no_std` / embedded targets;
   - AVX2 / AVX-512 performance for gateways.
4. **Validation paperwork, cheapest first.** CAVP algorithm certificates through ACVP testing come first, because
   NIAP evaluations require them. FIPS 140-3 module validation costs six figures and takes a year or more: do it
   only when a customer needs it, or ship source that fits inside the customer's module boundary.
5. **Drop-in integration.** An OpenSSL provider and a PKCS#11 interface, plus the protocol pieces CSfC selects:
   ML-KEM in IKEv2 (RFC 9370) and in TLS 1.3. Adoption cost decides deals more than benchmarks do.

## What not to do yet

Do not build a listable product. That means a Common Criteria evaluation plus an agreement with NSA, which is hard
to justify without an anchor customer.

## What this means for the prototype

| Gap | Today (`SCOPE.md`) | Needed for priority 1 |
|---|---|---|
| Schemes | Signature fixture only; ML-DSA via a pure-Python reference | A KEM fixture (ML-KEM-1024); LMS/XMSS verification; ML-DSA-87 pinned as the profile |
| Vectors | RFC 8032 Ed25519 vector | ACVP-format known-answer vectors for FIPS 203, FIPS 204 and SP 800-208 |
| Timing evidence | Latency distributions | A constant-time test with a positive control (a deliberately leaky adapter) |
| Adapters | Python modules | A C ABI adapter, since vendor code is C or Rust |
| Reports | PCI DSS and EU 2024/1774 template | A CNSA 2.0 selections template that names missing evidence |

None of these rows is built. They are the proposed backlog.

## Sources

- [CSfC Components List](https://www.nsa.gov/Resources/Commercial-Solutions-for-Classified-Program/components-list/) (not retrieved: HTTP 403)
- [CSfC Selections for IPsec VPN Client, 2026-08-04](https://www.nsa.gov/Portals/75/documents/CSfC%20Selections%20Updates%202026/CSfC_Selections_for_IPsec_VPN_Client-2026-08-04.pdf)
- [CSfC Selections for TLS Software Applications, 2026-08-13](https://www.nsa.gov/Portals/75/documents/CSfC%20Selections%20Updates%202026/CSfC%20Selections%20for%20TLS%20Software%20Applications-2026-08-13.pdf)
- [CSfC Key Management Requirements Annex v3.0.0](https://www.nsa.gov/Portals/75/documents/CSfC%20CP%20Updates%202026/(U)%20Key%20Management%20Requirements%20Annex%20v3.0.0.pdf)
- [atsec: CNSA compliance to be mandatory starting in 2027](https://atsec.de/cnsa-compliance-to-be-mandatory-starting-in-2027/)
- [atsec: What NIAP's latest CAVP mapping means for CNSA compliance](https://atsec.de/what-niaps-latest-cavp-mapping-means-for-cnsa-compliance/)
- [CSfC FAQ](https://www.nsa.gov/Resources/Commercial-Solutions-for-Classified-Program/faq/)
