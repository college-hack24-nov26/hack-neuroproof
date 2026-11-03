import { useEffect, useState } from "react";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { apiClient } from "../services/apiClient";
import { getErrorMessage } from "../utils/errors";

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
        description="Current Hardhat chain checks and historical zero-knowledge proof evidence."
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
