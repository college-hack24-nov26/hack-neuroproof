# V2 Proof Receipt Anchor

`NeuroProofReceiptAnchor` records an immutable attestation from an explicitly
authorized account that an off-chain Groth16 verification receipt was accepted.
It does not execute Groth16 verification and must never be presented as an
on-chain proof of MRI training, model quality, patient-data provenance, or
clinical safety.

## Receipt representation

The contract accepts only five non-zero `bytes32` commitments:

1. `federationRoundCommitment`: SHA-256 of
   `cerebrachain-v2:proof-receipt-anchor:round:v1:` plus the canonical UUID;
2. `modelVersionCommitment`: the registered model commitment;
3. `hospitalUpdateCommitment`: the protected update commitment;
4. `proofArtifactSha256`: SHA-256 of the protected public proof envelope; and
5. `verificationKeyId`: SHA-256 identifier for the pinned verification key.

The contract derives, rather than accepts, the receipt identifier:

```text
keccak256(abi.encode(RECEIPT_DOMAIN, round, model, update, proofHash, keyId))
```

This binds the event and stored receipt to its complete commitment tuple. The
anchor stores no patient data, images, credentials, tensors, witnesses, model
parameters, proving keys, or JWTs.

## Eligibility boundary

The backend mapping in
`services/api/app/modules/trust/proof_receipt_anchor.py` will produce anchor
arguments only when the update is accepted, cryptographically verified, has
complete chunk coverage, has a verification timestamp, and is eligible for
production aggregation. Consequently, STEP 162 development-only Groth16
receipts remain deliberately ineligible for anchoring.

The contract itself trusts an authorized anchoring account. A future deployment
must use a protected service account and an independently reviewed deployment
configuration; it does not convert an off-chain attestation into on-chain
Groth16 verification.

## Local tests

Install the exact declared package dependencies in an approved development
environment, then run:

```bash
npm install --ignore-scripts
npm test
```

The test suite compiles with `solc` and starts a fresh, ephemeral Hardhat node
on a dynamically selected loopback port. It does not use port 8545, a public
network, a persistent chain, database records, or real keys.

`scripts/deploy-synthetic-anchor.cjs` is a test-only helper used by the backend
integration test. It requires an explicit loopback RPC URL, deploys only to a
fresh test process, anchors synthetic commitments, and prints public synthetic
metadata for the Python adapter test. It must not be used for a persistent or
public deployment.

## Future read-only adapter

`ProofReceiptAnchorReadConfig` requires a pinned expected chain ID, contract
address, and SHA-256 of deployed runtime bytecode. A future reader must report
`unconfigured`, `unavailable`, `chain_id_mismatch`,
`contract_runtime_mismatch`, `receipt_missing`, or `confirmed` explicitly. It
must not send transactions.
