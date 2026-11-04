import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Card } from "../components/ui/Card";
import { apiClient } from "../services/apiClient";
import { getErrorMessage } from "../utils/errors";

const HEX32 = /^0x[0-9a-fA-F]{64}$/;

const DEVELOPMENT_CLASSIFICATION =
  "development_synthetic_offchain_verified";

type V3Receipt = {
  federation_round_commitment: string;
  model_version_commitment: string;
  hospital_update_commitment: string;
  proof_artifact_sha256: string;
  verification_key_id: string;
  attestation_status: string;
  anchored_at: number;
  anchored_block: number;
  attested_by: string;
};

type V3Lookup = {
  state: string;
  detail: string;
  rpc_available: boolean;
  chain_id: number | null;
  contract_address: string | null;
  runtime_bytecode_sha256: string | null;
  contract_identity_verified: boolean;
  receipt_id: string | null;
  receipt: V3Receipt | null;
  transaction_hash: string | null;
  transaction_block_number: number | null;
  confirmations: number | null;
  event_verified: boolean;
  verified_classification: string | null;
  development_only: boolean;
  production_eligible: boolean;
  offchain_groth16_verified: boolean;
  onchain_groth16_verified: boolean;
};

function lookupErrorMessage(cause: unknown): string {
  if (typeof cause === "object" && cause !== null && "status" in cause) {
    const status = (cause as { status: unknown }).status;

    if (status === 403) {
      return "Receipt Viewer authorization is required for V3 receipt lookup.";
    }

    if (status === 401) {
      return "Your session is unavailable or expired. Sign in again.";
    }

    if (status === 404) {
      return "The active backend does not expose the V3 receipt endpoint.";
    }
  }

  return getErrorMessage(cause);
}

function Metadata({
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

export function V3DevelopmentReceiptPanel() {
  const [receiptId, setReceiptId] = useState("");
  const [transactionHash, setTransactionHash] = useState("");
  const [result, setResult] = useState<V3Lookup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => activeRequest.current?.abort();
  }, []);

  function handleLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    activeRequest.current?.abort();
    activeRequest.current = null;

    setResult(null);
    setError(null);
    setLoading(false);

    const id = receiptId.trim().toLowerCase();
    const tx = transactionHash.trim().toLowerCase();

    if (!HEX32.test(id)) {
      setError("V3 receipt ID must contain exactly 32 hexadecimal bytes.");
      return;
    }

    if (!HEX32.test(tx)) {
      setError("V3 transaction hash must contain exactly 32 hexadecimal bytes.");
      return;
    }

    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);

    const route =
      `/trust/v3/receipts/${encodeURIComponent(id)}` +
      `?transaction_hash=${encodeURIComponent(tx)}`;

    async function executeLookup() {
      try {
        const response = await apiClient.request<V3Lookup>(
          route,
          { signal: controller.signal },
        );

        if (!controller.signal.aborted) {
          setResult(response);
        }
      } catch (cause: unknown) {
        if (!controller.signal.aborted) {
          setError(lookupErrorMessage(cause));
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void executeLookup().catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setError(lookupErrorMessage(cause));
        setLoading(false);
      }
    });
  }

  const fullyConfirmed =
    result !== null &&
    result.state === "confirmed" &&
    result.rpc_available === true &&
    result.contract_identity_verified === true &&
    result.event_verified === true &&
    result.verified_classification === DEVELOPMENT_CLASSIFICATION &&
    result.development_only === true &&
    result.production_eligible === false &&
    result.offchain_groth16_verified === false &&
    result.onchain_groth16_verified === false &&
    (result.confirmations ?? 0) >= 1 &&
    result.receipt !== null &&
    result.receipt.attestation_status === DEVELOPMENT_CLASSIFICATION;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">
            V3 Development Receipt Verification
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
            Look up an existing synthetic development receipt using the
            authenticated FastAPI service. This is read-only: no wallet
            connection or blockchain transaction is required.
          </p>
        </div>
        <span className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-100">
          V3 / Development only
        </span>
      </div>

      <div className="mt-4 rounded-lg border border-amber-400/25 bg-amber-400/5 p-4 text-sm leading-6 text-amber-100">
        This receipt records a development-only attestation. Groth16 proof
        verification occurred off-chain in a separate workflow; this API
        does not re-verify the proof. No on-chain Groth16 verification,
        actual hospital training proof, or clinical validation is claimed.
        The receipt is not production eligible.
      </div>

      <form onSubmit={handleLookup} className="mt-5 grid gap-4">
        <div>
          <label htmlFor="v3-receipt-id" className="block text-sm font-medium text-ink">
            V3 receipt ID
          </label>
          <input
            id="v3-receipt-id"
            type="text"
            value={receiptId}
            onChange={(event) => setReceiptId(event.target.value)}
            placeholder="0x… (32-byte V3 receipt ID)"
            autoComplete="off"
            spellCheck={false}
            maxLength={66}
            pattern="0x[0-9a-fA-F]{64}"
            required
            className="mt-2 w-full rounded-lg border border-border bg-slate-900/60 px-3 py-2 font-mono text-sm text-ink outline-none focus:border-cyan-400"
          />
        </div>

        <div>
          <label htmlFor="v3-transaction-hash" className="block text-sm font-medium text-ink">
            V3 transaction hash
          </label>
          <input
            id="v3-transaction-hash"
            type="text"
            value={transactionHash}
            onChange={(event) => setTransactionHash(event.target.value)}
            placeholder="0x… (anchoring transaction)"
            autoComplete="off"
            spellCheck={false}
            maxLength={66}
            pattern="0x[0-9a-fA-F]{64}"
            required
            className="mt-2 w-full rounded-lg border border-border bg-slate-900/60 px-3 py-2 font-mono text-sm text-ink outline-none focus:border-cyan-400"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg border border-cyan-400/35 bg-cyan-500/15 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Checking V3 receipt…" : "Check V3 receipt"}
          </button>
          <span className="text-xs text-muted">
            No automatic lookup. Receipt Viewer permission is enforced by the API.
          </span>
        </div>
      </form>

      {loading ? (
        <p role="status" className="mt-4 text-sm text-muted">
          Checking the pinned V3 contract and transaction…
        </p>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200"
        >
          {error}
        </p>
      ) : null}

      {result ? (
        <div aria-live="polite" className="mt-6 grid gap-5">
          <div className="rounded-lg border border-border bg-slate-900/40 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              V3 read-only lookup result
            </p>
            <p
              className={`mt-2 font-semibold ${
                fullyConfirmed ? "text-emerald-300" : "text-amber-200"
              }`}
            >
              {fullyConfirmed
                ? "Development receipt confirmed on-chain"
                : `Not fully confirmed: ${result.state}`}
            </p>
            <p className="mt-2 text-sm text-muted">{result.detail}</p>
          </div>

          {fullyConfirmed && result.receipt ? (
            <>
              <dl className="grid gap-5 sm:grid-cols-2">
                <Metadata label="V3 receipt identifier" value={result.receipt_id} />
                <Metadata label="Network chain ID" value={result.chain_id} />
                <Metadata label="V3 contract address" value={result.contract_address} />
                <Metadata
                  label="Runtime bytecode SHA256"
                  value={result.runtime_bytecode_sha256}
                />
                <Metadata label="Anchoring transaction" value={result.transaction_hash} />
                <Metadata label="Transaction block" value={result.transaction_block_number} />
                <Metadata label="Confirmations" value={result.confirmations} />
                <Metadata label="Development classification" value={result.verified_classification} />
              </dl>

              <div className="rounded-lg border border-border bg-slate-900/40 p-4">
                <h3 className="font-semibold text-ink">
                  Immutable development receipt commitments
                </h3>
                <dl className="mt-4 grid gap-5 sm:grid-cols-2">
                  <Metadata
                    label="Federation round commitment"
                    value={result.receipt.federation_round_commitment}
                  />
                  <Metadata
                    label="Model version commitment"
                    value={result.receipt.model_version_commitment}
                  />
                  <Metadata
                    label="Synthetic update commitment"
                    value={result.receipt.hospital_update_commitment}
                  />
                  <Metadata
                    label="Proof artifact SHA256"
                    value={result.receipt.proof_artifact_sha256}
                  />
                  <Metadata
                    label="Verification key identifier"
                    value={result.receipt.verification_key_id}
                  />
                  <Metadata label="Receipt block" value={result.receipt.anchored_block} />
                  <Metadata label="Attesting account" value={result.receipt.attested_by} />
                </dl>
              </div>

              <p className="rounded-lg border border-amber-400/25 bg-amber-400/5 p-4 text-sm text-amber-100">
                Blockchain anchoring verified. On-chain Groth16 verification:
                Not performed. Independent off-chain proof recheck by this API:
                Not performed. Production eligible: No.
              </p>
            </>
          ) : (
            <p className="text-sm text-amber-200">
              A confirmed development receipt has not been established by
              this lookup. No proof-validity claim is made.
            </p>
          )}
        </div>
      ) : null}
    </Card>
  );
}
