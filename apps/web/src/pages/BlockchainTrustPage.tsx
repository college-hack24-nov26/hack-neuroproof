import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { apiClient } from "../services/apiClient";
import { getErrorMessage } from "../utils/errors";
import { getV2LookupErrorMessage } from "../utils/trustLookup";

type TrustSummary = {
  network: {
    rpc_available: boolean;
    chain_id: number | null;
    latest_block: number | null;
    genesis_matches: boolean;
  };
  contract: {
    name: string | null;
    address: string | null;
    runtime_hash_matches: boolean;
    code_present: boolean;
  };
  transactions: {
    deployment_hash: string | null;
    deployment_confirmed: boolean;
    anchoring_hash: string | null;
    anchoring_confirmed: boolean;
  };
  proof_evidence: {
    recorded_jobs: number | null;
    proofset_total: number | null;
    hospital_count: number | null;
    merkle_root_matches_historical_record: boolean;
    merkle_root: string | null;
    historical_blockchain_anchored_flag: boolean;
    onchain_proof_verification_count: number;
    proofs_reverified_during_anchoring: number;
    verification_scope: string | null;
  };
  verification: {
    current_anchor_transaction_confirmed: boolean;
    individual_groth16_proofs_verified_live: boolean;
  };
  disclaimer: string;
};


// Mirrors the protected V2 receipt-read API response in services/api/app/schemas/trust.py.
// This is separate from the legacy /trust/summary response above.
type V2AnchorLookupState =
  | "unconfigured"
  | "unavailable"
  | "chain_id_mismatch"
  | "contract_code_missing"
  | "contract_runtime_mismatch"
  | "invalid_receipt_id"
  | "invalid_transaction_hash"
  | "receipt_mismatch"
  | "receipt_missing"
  | "receipt_found"
  | "transaction_missing"
  | "transaction_pending"
  | "event_mismatch"
  | "malformed_rpc_response"
  | "confirmed";

type V2AnchorReceipt = {
  federation_round_commitment: string;
  model_version_commitment: string;
  hospital_update_commitment: string;
  proof_artifact_sha256: string;
  verification_key_id: string;
  attestation_status: "offchain_groth16_verified";
  anchored_at: number;
  anchored_block: number;
  attested_by: string;
};

type V2AnchorLookup = {
  state: V2AnchorLookupState;
  detail: string;
  rpc_available: boolean;
  chain_id: number | null;
  contract_address: string | null;
  runtime_bytecode_sha256: string | null;
  contract_identity_verified: boolean;
  receipt_id: string | null;
  receipt: V2AnchorReceipt | null;
  transaction_hash: string | null;
  transaction_block_number: number | null;
  confirmations: number | null;
  event_verified: boolean;
  offchain_groth16_verified: boolean;
  onchain_groth16_verified: false;
};

const BYTES32_HEX = /^0x[0-9a-fA-F]{64}$/;

const V2_LOOKUP_LABELS: Record<V2AnchorLookupState, string> = {
  unconfigured: "V2 anchor not configured",
  unavailable: "Blockchain RPC unavailable",
  chain_id_mismatch: "Unexpected blockchain network",
  contract_code_missing: "Contract code missing",
  contract_runtime_mismatch: "Contract bytecode mismatch",
  invalid_receipt_id: "Invalid receipt ID",
  invalid_transaction_hash: "Invalid transaction hash",
  receipt_mismatch: "Receipt commitments mismatch",
  receipt_missing: "No on-chain receipt found",
  receipt_found: "Receipt found; transaction not confirmed by this lookup",
  transaction_missing: "Transaction not found",
  transaction_pending: "Transaction awaiting confirmations",
  event_mismatch: "Receipt event mismatch",
  malformed_rpc_response: "Invalid blockchain RPC response",
  confirmed: "Anchoring transaction confirmed",
};

function Status({
  value,
  success = "Confirmed",
  failure = "Not confirmed",
}: {
  value: boolean;
  success?: string;
  failure?: string;
}) {
  return (
    <span
      className={
        value
          ? "font-semibold text-emerald-300"
          : "font-semibold text-amber-300"
      }
    >
      {value ? success : failure}
    </span>
  );
}

function Detail({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </dt>
      <dd className="mt-2 break-all font-mono text-sm text-ink">
        {value ?? "Not available"}
      </dd>
    </div>
  );
}

export function BlockchainTrustPage() {
  const [data, setData] = useState<TrustSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  // V2 receipt lookup is independent of the historical trust summary.
  // Never request on mount: an ordinary Hospital Admin is not necessarily a receipt viewer.
  const [receiptId, setReceiptId] = useState("");
  const [transactionHash, setTransactionHash] = useState("");
  const [lookupResult, setLookupResult] = useState<V2AnchorLookup | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [lookupLoading, setLookupLoading] = useState(false);
  const lookupControllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => lookupControllerRef.current?.abort(), []);

  function handleV2Lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    lookupControllerRef.current?.abort();
    lookupControllerRef.current = null;
    setLookupResult(null);
    setLookupError(null);
    setLookupLoading(false);

    const id = receiptId.trim();
    const tx = transactionHash.trim();
    if (!BYTES32_HEX.test(id)) {
      setLookupError("Receipt ID must be 0x followed by exactly 64 hexadecimal characters.");
      return;
    }
    if (tx && !BYTES32_HEX.test(tx)) {
      setLookupError("Transaction hash must be 0x followed by exactly 64 hexadecimal characters.");
      return;
    }

    const controller = new AbortController();
    lookupControllerRef.current = controller;
    setLookupLoading(true);
    const query = tx ? `?transaction_hash=${encodeURIComponent(tx.toLowerCase())}` : "";
    apiClient
      .request<V2AnchorLookup>(
        `/trust/v2/receipts/${encodeURIComponent(id.toLowerCase())}${query}`,
        { signal: controller.signal },
      )
      .then((result) => {
        if (!controller.signal.aborted) setLookupResult(result);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setLookupError(getV2LookupErrorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLookupLoading(false);
      });
  }

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setLoading(true);
    setError(null);
    setData(null);

    apiClient
      .request<TrustSummary>("/trust/summary", {
        signal: controller.signal,
      })
      .then((result) => {
        if (active) setData(result);
      })
      .catch((cause: unknown) => {
        if (active && !controller.signal.aborted) {
          setError(getErrorMessage(cause));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [refreshKey]);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Blockchain & ZKP Trust"
        description="Read-only V2 receipt lookup and historical blockchain/ZKP evidence."
      />

      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-muted">
          Read-only verification. No transactions are submitted.
        </p>

        <button
          type="button"
          onClick={() => setRefreshKey((value) => value + 1)}
          className="rounded-lg border border-violet-400/40 bg-violet-500/20 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500/30"
        >
          Refresh verification
        </button>
      </div>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-ink">
              V2 Proof Receipt Lookup
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Read an existing V2 receipt from a pinned blockchain contract.
              This action is read-only and requires server-approved Receipt Viewer access.
              It does not submit transactions or verify Groth16 proofs on-chain.
            </p>
          </div>
          <span className="rounded-full border border-violet-400/30 bg-violet-500/10 px-3 py-1 text-xs font-semibold text-violet-200">
            V2 / Receipt Viewer
          </span>
        </div>

        <form onSubmit={handleV2Lookup} className="mt-5 grid gap-4">
          <div>
            <label htmlFor="v2-receipt-id" className="block text-sm font-medium text-ink">
              Receipt ID <span className="text-rose-300">*</span>
            </label>
            <input
              id="v2-receipt-id"
              type="text"
              value={receiptId}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setReceiptId(event.target.value)}
              placeholder="0x… (32-byte receipt identifier)"
              autoComplete="off"
              spellCheck={false}
              maxLength={66}
              required
              pattern="0x[0-9a-fA-F]{64}"
              className="mt-2 w-full rounded-lg border border-border bg-slate-900/60 px-3 py-2 font-mono text-sm text-ink outline-none focus:border-violet-400"
            />
          </div>
          <div>
            <label htmlFor="v2-transaction-hash" className="block text-sm font-medium text-ink">
              Anchoring transaction hash (optional)
            </label>
            <input
              id="v2-transaction-hash"
              type="text"
              value={transactionHash}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setTransactionHash(event.target.value)}
              placeholder="0x… (include to check transaction and event)"
              autoComplete="off"
              spellCheck={false}
              maxLength={66}
              pattern="0x[0-9a-fA-F]{64}"
              className="mt-2 w-full rounded-lg border border-border bg-slate-900/60 px-3 py-2 font-mono text-sm text-ink outline-none focus:border-violet-400"
            />
            <p className="mt-2 text-xs text-muted">
              Transaction confirmation cannot be established without a transaction hash.
              Receipt lookup alone does not prove an anchoring transaction was confirmed.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={lookupLoading}
              className="rounded-lg border border-violet-400/40 bg-violet-500/20 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500/30 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {lookupLoading ? "Checking receipt…" : "Check V2 receipt"}
            </button>
            <span className="text-xs text-muted">
              No receipt is queried automatically. The API enforces Receipt Viewer authorization.
            </span>
          </div>
        </form>

        {lookupLoading ? (
          <p className="mt-5 text-sm text-muted" role="status">
            Inspecting pinned V2 contract and receipt…
          </p>
        ) : null}

        {lookupError ? (
          <p className="mt-5 rounded-lg border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200" role="alert">
            {lookupError}
          </p>
        ) : null}

        {lookupResult ? (
          <div className="mt-6 grid gap-5" aria-live="polite">
            <div className="rounded-lg border border-border bg-slate-900/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                Read-only lookup result
              </p>
              <p className={`mt-2 text-base font-semibold ${
                lookupResult.state === "confirmed"
                  ? "text-emerald-300"
                  : lookupResult.state === "receipt_found"
                    ? "text-cyan-200"
                    : "text-amber-200"
              }`}>
                {V2_LOOKUP_LABELS[lookupResult.state] ?? "Unknown receipt state"}
              </p>
              <p className="mt-2 text-sm text-muted">{lookupResult.detail}</p>
            </div>

            <dl className="grid gap-5 sm:grid-cols-2">
              <Detail label="Receipt ID" value={lookupResult.receipt_id} />
              <Detail label="Chain ID" value={lookupResult.chain_id} />
              <Detail label="Contract address" value={lookupResult.contract_address} />
              <Detail label="Runtime bytecode SHA256" value={lookupResult.runtime_bytecode_sha256} />
            </dl>

            <div className="grid gap-3 text-sm text-muted sm:grid-cols-2">
              <p>
                RPC: <Status value={lookupResult.rpc_available} success="Connected" failure="Unavailable" />
              </p>
              <p>
                Pinned contract identity: <Status value={lookupResult.contract_identity_verified} success="Verified" failure="Not verified" />
              </p>
              <p>
                Receipt event matches: <Status value={lookupResult.event_verified} success="Yes" failure="Not established" />
              </p>
              <p>
                Anchoring transaction: <Status
                  value={lookupResult.state === "confirmed" && lookupResult.contract_identity_verified && lookupResult.event_verified}
                  success="Confirmed by lookup"
                  failure="Not confirmed by lookup"
                />
              </p>
            </div>

            <dl className="grid gap-5 sm:grid-cols-2">
              <Detail label="Transaction hash" value={lookupResult.transaction_hash} />
              <Detail label="Transaction block" value={lookupResult.transaction_block_number} />
              <Detail label="Confirmations" value={lookupResult.confirmations} />
            </dl>

            {lookupResult.receipt ? (
              <div className="rounded-lg border border-border bg-slate-900/40 p-4">
                <h3 className="font-semibold text-ink">Immutable on-chain receipt metadata</h3>
                <dl className="mt-5 grid gap-5 sm:grid-cols-2">
                  <Detail label="Federation round commitment" value={lookupResult.receipt.federation_round_commitment} />
                  <Detail label="Model version commitment" value={lookupResult.receipt.model_version_commitment} />
                  <Detail label="Hospital/update commitment" value={lookupResult.receipt.hospital_update_commitment} />
                  <Detail label="Proof artifact SHA256 (bytes32)" value={lookupResult.receipt.proof_artifact_sha256} />
                  <Detail label="Verification key identifier" value={lookupResult.receipt.verification_key_id} />
                  <Detail label="Off-chain verification attestation" value={lookupResult.receipt.attestation_status} />
                  <Detail label="Anchor block" value={lookupResult.receipt.anchored_block} />
                  <Detail label="Anchor timestamp (Unix seconds)" value={lookupResult.receipt.anchored_at} />
                  <Detail label="Attesting address" value={lookupResult.receipt.attested_by} />
                </dl>
              </div>
            ) : null}

            <div className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-4 text-sm leading-6 text-amber-100">
              <p className="font-semibold">Verification scope</p>
              <p className="mt-2">
                Off-chain Groth16 verification attested by this receipt:{" "}
                <Status
                  value={lookupResult.offchain_groth16_verified}
                  success="Claim recorded on-chain"
                  failure="No attestation available"
                />
                . This read-only lookup does not independently re-run the proof verifier.
              </p>
              <p className="mt-2">
                On-chain Groth16 proof verification: <strong>Not performed</strong>.
                Blockchain anchoring does not establish MRI training correctness or clinical validity.
              </p>
            </div>
          </div>
        ) : null}
      </Card>

      {loading ? (
        <Card>
          <p className="text-muted">Checking blockchain evidence…</p>
        </Card>
      ) : null}

      {error ? (
        <Card>
          <p className="text-rose-300" role="alert">
            Trust API error: {error}
          </p>
        </Card>
      ) : null}

      {data ? (
        <>
          <div className="grid gap-5 md:grid-cols-3">
            <Card>
              <p className="text-sm text-muted">Hardhat Network</p>
              <p className="mt-3 text-3xl font-semibold text-ink">
                {data.network.chain_id ?? "—"}
              </p>
              <p className="mt-3 text-sm text-muted">
                RPC:{" "}
                <Status
                  value={data.network.rpc_available}
                  success="Connected"
                  failure="Unavailable"
                />
              </p>
            </Card>

            <Card>
              <p className="text-sm text-muted">Blockchain Anchor</p>
              <p className="mt-3 text-xl font-semibold">
                <Status
                  value={
                    data.verification.current_anchor_transaction_confirmed
                  }
                />
              </p>
              <p className="mt-3 text-sm text-muted">
                Current-chain transaction evidence
              </p>
            </Card>

            <Card>
              <p className="text-sm text-muted">Groth16 Proof Jobs</p>
              <p className="mt-3 text-3xl font-semibold text-ink">
                {data.proof_evidence.recorded_jobs?.toLocaleString() ?? "—"}
              </p>
              <p className="mt-3 text-sm text-amber-200">
                Recorded jobs ≠ on-chain verified proofs
              </p>
            </Card>
          </div>

          <Card>
            <h2 className="text-lg font-semibold text-ink">
              Blockchain Network
            </h2>

            <dl className="mt-5 grid gap-5 sm:grid-cols-2">
              <Detail
                label="Chain ID"
                value={data.network.chain_id}
              />
              <Detail
                label="Latest block"
                value={data.network.latest_block}
              />
            </dl>

            <p className="mt-5 text-sm text-muted">
              Genesis hash matches deployment evidence:{" "}
              <Status value={data.network.genesis_matches} />
            </p>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-ink">
              Smart Contract Verification
            </h2>

            <dl className="mt-5 grid gap-5 sm:grid-cols-2">
              <Detail
                label="Contract"
                value={data.contract.name}
              />
              <Detail
                label="Contract address"
                value={data.contract.address}
              />
            </dl>

            <div className="mt-5 grid gap-3 text-sm text-muted sm:grid-cols-2">
              <p>
                Contract bytecode present:{" "}
                <Status value={data.contract.code_present} />
              </p>
              <p>
                Runtime SHA256 matches:{" "}
                <Status value={data.contract.runtime_hash_matches} />
              </p>
            </div>
          </Card>

          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <h2 className="text-lg font-semibold text-ink">
                Contract Deployment
              </h2>

              <p className="mt-3 text-sm text-muted">
                Transaction:{" "}
                <Status
                  value={data.transactions.deployment_confirmed}
                />
              </p>

              <dl className="mt-5">
                <Detail
                  label="Deployment transaction hash"
                  value={data.transactions.deployment_hash}
                />
              </dl>
            </Card>

            <Card>
              <h2 className="text-lg font-semibold text-ink">
                Blockchain Anchoring
              </h2>

              <p className="mt-3 text-sm text-muted">
                Transaction:{" "}
                <Status
                  value={data.transactions.anchoring_confirmed}
                />
              </p>

              <dl className="mt-5">
                <Detail
                  label="Anchoring transaction hash"
                  value={data.transactions.anchoring_hash}
                />
              </dl>
            </Card>
          </div>

          <Card>
            <h2 className="text-lg font-semibold text-ink">
              Historical ZKP Evidence
            </h2>

            <dl className="mt-5 grid gap-5 sm:grid-cols-3">
              <Detail
                label="Recorded proof jobs"
                value={data.proof_evidence.recorded_jobs}
              />
              <Detail
                label="Proofset total"
                value={data.proof_evidence.proofset_total}
              />
              <Detail
                label="Participating hospitals"
                value={data.proof_evidence.hospital_count}
              />
              <Detail
                label="Individual on-chain verifications"
                value={
                  data.proof_evidence.onchain_proof_verification_count
                }
              />
              <Detail
                label="Proofs reverified during anchoring"
                value={
                  data.proof_evidence.proofs_reverified_during_anchoring
                }
              />
              <Detail
                label="Verification scope"
                value={data.proof_evidence.verification_scope}
              />
            </dl>

            <div className="mt-5 rounded-lg border border-border bg-slate-900/50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                Historical Proof Merkle Root
              </p>
              <p className="mt-2 break-all font-mono text-xs text-cyan-200">
                {data.proof_evidence.merkle_root ?? "Not available"}
              </p>
            </div>

            <div className="mt-5 grid gap-3 text-sm text-muted">
              <p>
                Merkle root matches historical anchoring record:{" "}
                <Status
                  value={
                    data.proof_evidence
                      .merkle_root_matches_historical_record
                  }
                />
              </p>
              <p>
                Original proofset anchored flag:{" "}
                <Status
                  value={
                    data.proof_evidence
                      .historical_blockchain_anchored_flag
                  }
                  success="True"
                  failure="False"
                />
              </p>
              <p>
                Individual Groth16 proofs verified live:{" "}
                <Status
                  value={
                    data.verification
                      .individual_groth16_proofs_verified_live
                  }
                  success="Yes"
                  failure="Not performed"
                />
              </p>
            </div>
          </Card>

          <Card>
            <h2 className="font-semibold text-amber-200">
              Verification Scope & Limitations
            </h2>
            <p className="mt-3 text-sm leading-6 text-muted">
              {data.disclaimer}
            </p>
            <p className="mt-3 text-xs text-muted">
              This dashboard confirms recorded evidence and selected
              live-chain conditions. It does not independently verify
              all 1,800 Groth16 proofs or establish clinical validity.
            </p>
          </Card>
        </>
      ) : null}
    </div>
  );
}
