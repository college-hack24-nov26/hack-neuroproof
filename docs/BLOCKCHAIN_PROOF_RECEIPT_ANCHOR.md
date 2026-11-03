# V2 Blockchain Proof Receipt Anchor

## Scope

`NeuroProofReceiptAnchor` is the V2 contract boundary for recording an
authorized off-chain proof-verification receipt. It does not include a Groth16
verifier contract. The legacy verifier is incompatible because it expects five
public signals while V2 `quantized-update-chunk-v1` has seven.

An anchored receipt means only that an authorized account attested that the
specified off-chain receipt was verified. It does not prove complete 3D U-Net
training correctness, data provenance, MRI diagnosis, clinical accuracy, or
the security of the off-chain verifier.

## Authorization and immutability

- The deployment owner explicitly authorizes anchoring accounts.
- Only an authorized anchoring account can create a receipt.
- Receipt IDs are canonical, deterministic hashes of all five commitments.
- A receipt ID can be created once and cannot be overwritten or deleted.
- Authorization changes and ownership transfers emit events.

## Backend eligibility mapping

The pure mapping in
`services/api/app/modules/trust/proof_receipt_anchor.py` accepts only a
`FederationUpdateArtifact` that is:

1. `accepted`;
2. cryptographically `verified`;
3. complete across required chunks;
4. explicitly production aggregation eligible; and
5. timestamped as cryptographically verified.

It maps the model/update/proof/key SHA-256 values directly to `bytes32` and
derives a domain-separated round commitment from the canonical UUID. The
Solidity contract derives the final receipt ID using ABI encoding and Keccak.
Development-only Groth16 results remain rejected by this mapping because they
are not aggregation eligible.

## Read-only chain reconciliation

Before displaying an anchored V2 receipt, a future adapter must validate:

- a configured RPC endpoint;
- the expected chain ID;
- the exact configured contract address;
- SHA-256 of `eth_getCode` against the approved runtime-bytecode hash; and
- `receiptExists` / `getReceipt` results matching the expected commitments.

It must distinguish an unconfigured chain, unavailable RPC, wrong chain ID,
wrong contract runtime, and missing receipt. Transaction submission and any
database persistence of a transaction hash or block number are intentionally
out of scope and require separate design review and an additive migration.

## STEP 164 read-only adapter

`services/api/app/modules/trust/v2_anchor_rpc.py` now implements the V2 ABI
using only these read-only JSON-RPC methods: `eth_chainId`, `eth_blockNumber`,
`eth_getCode`, `eth_call`, `eth_getTransactionReceipt`, and
`eth_getTransactionByHash`. It has no signing, deployment,
`eth_sendTransaction`, or `eth_sendRawTransaction` capability.

Function selectors, the `ReceiptAnchored` event topic, and canonical receipt
identifiers use Ethereum **Keccak-256**. Runtime-bytecode pinning instead uses
an explicitly separate **SHA-256** digest of raw `eth_getCode` bytes. SHA-256
is never used as an Ethereum selector or receipt identifier.

The protected V2 receipt route is:

```text
GET /api/v1/trust/v2/receipts/{receipt_id}?transaction_hash={optional_hash}
```

The route now accepts either an existing federation operator or a dedicated,
server-configured Hospital Admin listed in
`CEREBRACHAIN_PROOF_RECEIPT_READER_EMAILS`. The dedicated reader allowlist is
empty by default and grants access only to this read-only route; it does not
grant model registration, round control, global federation summary access, or
cross-hospital update metadata access. The route still exposes an existing
global receipt identifier and commitment tuple when one is found, so viewer
identities must be explicitly approved and receipt identifiers must not be
treated as public discovery data.

It verifies the pinned chain ID and runtime hash, calls `receiptExists`,
`getReceipt`, and `computeReceiptId`, and validates matching event data plus
the configured confirmation count when a transaction hash is supplied. It
returns explicit unavailable, mismatch, missing, pending, and confirmed states.

Required server-side configuration is intentionally blank by default:

- `CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_RPC_URL`
- `CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_EXPECTED_CHAIN_ID`
- `CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_CONTRACT_ADDRESS`
- `CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_RUNTIME_CODE_SHA256`
- `CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_ABI_VERSION=neuroproof-receipt-anchor-v1`

Optional bounded values are `..._REQUIRED_CONFIRMATIONS` and
`..._TIMEOUT_SECONDS`. The dashboard never queries a V2 receipt automatically
and preserves the separate historical evidence section. A hospital-scoped V2
receipt view requires a reviewed server-side association between an update and
the deployed receipt; no such association is inferred from a commitment.
